"""Optional boto3 adapter for live Lake Formation inventory and apply."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .models import CurrentState, DesiredState, Grant, LFTagDefinition, ResourceRef, ResourceTagAssignment
from .planner import Change, Plan


@dataclass(frozen=True)
class ApplyResult:
    """Result of applying or dry-running a single change."""

    action: str
    target: str
    applied: bool
    response: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "applied": self.applied,
            "response": dict(self.response),
        }


class AWSLakeFormationAdapter:
    """Thin boto3-backed adapter for Lake Formation operations."""

    def __init__(self, lakeformation_client: Any, *, catalog_id: Optional[str] = None) -> None:
        self.lakeformation = lakeformation_client
        self.catalog_id = catalog_id

    @classmethod
    def from_boto3(
        cls,
        *,
        profile_name: Optional[str] = None,
        region_name: Optional[str] = None,
        catalog_id: Optional[str] = None,
    ) -> "AWSLakeFormationAdapter":
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for live AWS operations. Install lfguard[aws]."
            ) from exc
        session = boto3.Session(profile_name=profile_name, region_name=region_name)
        return cls(session.client("lakeformation"), catalog_id=catalog_id)

    def load_current_state_for(self, desired: DesiredState) -> CurrentState:
        """Load only the current AWS surface needed to compare with desired state."""

        lf_tags = list(self._load_lf_tags(desired))
        resource_tags = list(self._load_resource_tags(desired))
        grants = list(self._load_grants(desired))
        return CurrentState(lf_tags=tuple(lf_tags), resource_tags=tuple(resource_tags), grants=tuple(grants))

    def apply(self, change_plan: Plan, *, dry_run: bool = True, allow_destructive: bool = False) -> List[ApplyResult]:
        results: List[ApplyResult] = []
        for change in change_plan.executable_changes(allow_destructive=allow_destructive):
            if dry_run:
                results.append(ApplyResult(change.action, change.target, False, {"dry_run": True}))
                continue
            results.append(self._apply_change(change))
        return results

    def _load_lf_tags(self, desired: DesiredState) -> Iterable[LFTagDefinition]:
        for tag in desired.lf_tags:
            kwargs = self._with_catalog_id({"TagKey": tag.key})
            try:
                response = self.lakeformation.get_lf_tag(**kwargs)
            except Exception as exc:
                if _is_not_found(exc):
                    continue
                raise
            values = response.get("TagValues", ())
            if values:
                yield LFTagDefinition(tag.key, tuple(values))

    def _load_resource_tags(self, desired: DesiredState) -> Iterable[ResourceTagAssignment]:
        resources = {assignment.resource for assignment in desired.resource_tags}
        resources.update(grant.resource for grant in desired.grants if grant.resource.kind != "lf_tag_policy")
        for resource in sorted(resources):
            kwargs = self._with_catalog_id({"Resource": to_lf_resource(resource)})
            try:
                response = self.lakeformation.get_resource_lf_tags(**kwargs)
            except Exception as exc:
                if _is_not_found(exc):
                    continue
                raise
            tags = _extract_resource_tags(response)
            if tags:
                yield ResourceTagAssignment(resource=resource, tags=tags)

    def _load_grants(self, desired: DesiredState) -> Iterable[Grant]:
        seen = set()
        for desired_grant in desired.grants:
            key = desired_grant.identity
            if key in seen:
                continue
            seen.add(key)
            kwargs = {
                "Principal": {"DataLakePrincipalIdentifier": desired_grant.principal},
                "Resource": to_lf_resource(desired_grant.resource),
                "MaxResults": 100,
            }
            kwargs = self._with_catalog_id(kwargs)
            for item in self._list_permissions(kwargs):
                principal = item.get("Principal", {}).get("DataLakePrincipalIdentifier", desired_grant.principal)
                resource = from_lf_resource(item.get("Resource", {})) or desired_grant.resource
                permissions = tuple(item.get("Permissions", ()))
                grantables = tuple(item.get("PermissionsWithGrantOption", ()))
                if permissions:
                    yield Grant(principal=principal, resource=resource, permissions=permissions, grantable_permissions=grantables)

    def _list_permissions(self, kwargs: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        if hasattr(self.lakeformation, "get_paginator"):
            try:
                paginator = self.lakeformation.get_paginator("list_permissions")
                for page in paginator.paginate(**dict(kwargs)):
                    for item in page.get("PrincipalResourcePermissions", ()):
                        yield item
                return
            except Exception as exc:
                if not _is_operation_not_pageable(exc):
                    raise
        next_token = None
        while True:
            request = dict(kwargs)
            if next_token:
                request["NextToken"] = next_token
            response = self.lakeformation.list_permissions(**request)
            for item in response.get("PrincipalResourcePermissions", ()):
                yield item
            next_token = response.get("NextToken")
            if not next_token:
                break

    def _apply_change(self, change: Change) -> ApplyResult:
        action = change.action
        payload = dict(change.payload)
        if action == "lf_tag.create":
            response = self.lakeformation.create_lf_tag(**self._with_catalog_id({
                "TagKey": payload["tag_key"],
                "TagValues": payload["tag_values"],
            }))
        elif action == "lf_tag.add_values":
            response = self.lakeformation.update_lf_tag(**self._with_catalog_id({
                "TagKey": payload["tag_key"],
                "TagValuesToAdd": payload["tag_values"],
            }))
        elif action == "lf_tag.remove_values":
            response = self.lakeformation.update_lf_tag(**self._with_catalog_id({
                "TagKey": payload["tag_key"],
                "TagValuesToDelete": payload["tag_values"],
            }))
        elif action == "resource_tag.add_values":
            response = self.lakeformation.add_lf_tags_to_resource(**self._with_catalog_id({
                "Resource": to_lf_resource(ResourceRef.from_dict(payload["resource"])),
                "LFTags": _lf_tag_pairs(payload["tags"]),
            }))
        elif action == "resource_tag.remove_values":
            response = self.lakeformation.remove_lf_tags_from_resource(**self._with_catalog_id({
                "Resource": to_lf_resource(ResourceRef.from_dict(payload["resource"])),
                "LFTags": _lf_tag_pairs(payload["tags"]),
            }))
        elif action == "grant.add_permissions":
            response = self.lakeformation.grant_permissions(**self._with_catalog_id({
                "Principal": {"DataLakePrincipalIdentifier": payload["principal"]},
                "Resource": to_lf_resource(ResourceRef.from_dict(payload["resource"])),
                "Permissions": payload.get("permissions", ()),
                "PermissionsWithGrantOption": payload.get("grantable_permissions", ()),
            }))
        elif action == "grant.revoke_permissions":
            response = self.lakeformation.revoke_permissions(**self._with_catalog_id({
                "Principal": {"DataLakePrincipalIdentifier": payload["principal"]},
                "Resource": to_lf_resource(ResourceRef.from_dict(payload["resource"])),
                "Permissions": payload.get("permissions", ()),
                "PermissionsWithGrantOption": payload.get("grantable_permissions", ()),
            }))
        else:
            raise ValueError("Unsupported change action: {}".format(action))
        return ApplyResult(action=change.action, target=change.target, applied=True, response=response or {})

    def _with_catalog_id(self, kwargs: Mapping[str, Any]) -> Dict[str, Any]:
        request = dict(kwargs)
        if self.catalog_id:
            request.setdefault("CatalogId", self.catalog_id)
        return request


def to_lf_resource(resource: ResourceRef) -> Dict[str, Any]:
    if resource.kind == "catalog":
        return {"Catalog": {}}
    if resource.kind == "database":
        return {"Database": _catalog_scoped({"Name": resource.database_name}, resource)}
    if resource.kind == "table":
        return {"Table": _catalog_scoped({
            "DatabaseName": resource.database_name,
            "Name": resource.table_name,
        }, resource)}
    if resource.kind == "table_with_columns":
        return {"TableWithColumns": _catalog_scoped({
            "DatabaseName": resource.database_name,
            "Name": resource.table_name,
            "ColumnNames": list(resource.columns),
        }, resource)}
    if resource.kind == "data_location":
        return {"DataLocation": _catalog_scoped({"ResourceArn": resource.location}, resource)}
    if resource.kind == "lf_tag_policy":
        return {
            "LFTagPolicy": {
                "ResourceType": resource.resource_type,
                "Expression": [
                    {"TagKey": item.key, "TagValues": list(item.values)}
                    for item in resource.expression
                ],
            }
        }
    raise ValueError("Unsupported resource kind: {}".format(resource.kind))


def from_lf_resource(raw: Mapping[str, Any]) -> Optional[ResourceRef]:
    if "Catalog" in raw:
        return ResourceRef(kind="catalog")
    if "Database" in raw:
        item = raw["Database"]
        return ResourceRef(kind="database", database_name=item.get("Name"), catalog_id=item.get("CatalogId"))
    if "Table" in raw:
        item = raw["Table"]
        return ResourceRef(kind="table", database_name=item.get("DatabaseName"), table_name=item.get("Name"), catalog_id=item.get("CatalogId"))
    if "TableWithColumns" in raw:
        item = raw["TableWithColumns"]
        return ResourceRef(
            kind="table_with_columns",
            database_name=item.get("DatabaseName"),
            table_name=item.get("Name"),
            columns=tuple(item.get("ColumnNames", ())),
            catalog_id=item.get("CatalogId"),
        )
    if "DataLocation" in raw:
        item = raw["DataLocation"]
        return ResourceRef(kind="data_location", location=item.get("ResourceArn"), catalog_id=item.get("CatalogId"))
    if "LFTagPolicy" in raw:
        item = raw["LFTagPolicy"]
        return ResourceRef.from_dict({
            "kind": "lf_tag_policy",
            "resource_type": item.get("ResourceType"),
            "expression": {
                expr.get("TagKey"): expr.get("TagValues", ())
                for expr in item.get("Expression", ())
            },
        })
    return None


def _catalog_scoped(data: Mapping[str, Any], resource: ResourceRef) -> Dict[str, Any]:
    result = {key: value for key, value in data.items() if value not in (None, "")}
    if resource.catalog_id:
        result["CatalogId"] = resource.catalog_id
    return result


def _lf_tag_pairs(tags: Mapping[str, Iterable[str]]) -> List[Dict[str, Any]]:
    return [{"TagKey": key, "TagValues": list(values)} for key, values in sorted(tags.items())]


def _extract_resource_tags(response: Mapping[str, Any]) -> Dict[str, frozenset]:
    tags: Dict[str, set] = {}
    for key in ("LFTagOnDatabase", "LFTagsOnTable"):
        _merge_lf_tag_pairs(tags, response.get(key, ()))
    for column_tags in response.get("LFTagsOnColumns", ()):
        _merge_lf_tag_pairs(tags, column_tags.get("LFTags", ()))
    return {key: frozenset(values) for key, values in tags.items()}


def _merge_lf_tag_pairs(target: Dict[str, set], pairs: Iterable[Mapping[str, Any]]) -> None:
    for pair in pairs:
        key = pair.get("TagKey")
        values = pair.get("TagValues", ())
        if key and values:
            target.setdefault(str(key), set()).update(str(value) for value in values)


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    code = response.get("Error", {}).get("Code") if isinstance(response, Mapping) else None
    return code in {"EntityNotFoundException", "ResourceNotFoundException", "GlueEncryptionException"}


def _is_operation_not_pageable(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"OperationNotPageableError", "PaginationError"}
