"""Conservative diff engine for Lake Formation guardrails."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Tuple

from .models import CurrentState, DesiredState, Grant, LFTagDefinition, ResourceRef, ResourceTagAssignment


@dataclass(frozen=True)
class PlanOptions:
    """Controls whether destructive drift remediation is included in a plan."""

    allow_lf_tag_value_removals: bool = False
    allow_resource_tag_removals: bool = False
    allow_permission_revokes: bool = False


@dataclass(frozen=True)
class Change:
    """Single executable or reviewable Lake Formation change."""

    action: str
    target: str
    reason: str
    payload: Mapping[str, Any]
    destructive: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "reason": self.reason,
            "destructive": self.destructive,
            "payload": _json_ready(self.payload),
        }


@dataclass(frozen=True)
class Plan:
    """Ordered collection of changes required to converge current to desired state."""

    changes: Tuple[Change, ...]

    @property
    def destructive_changes(self) -> Tuple[Change, ...]:
        return tuple(change for change in self.changes if change.destructive)

    @property
    def safe_changes(self) -> Tuple[Change, ...]:
        return tuple(change for change in self.changes if not change.destructive)

    def executable_changes(self, *, allow_destructive: bool = False) -> Tuple[Change, ...]:
        if allow_destructive:
            return self.changes
        return self.safe_changes

    def summary(self) -> Dict[str, int]:
        return {
            "total": len(self.changes),
            "safe": len(self.safe_changes),
            "destructive": len(self.destructive_changes),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary(),
            "changes": [change.to_dict() for change in self.changes],
        }


def plan(desired: DesiredState, current: CurrentState, options: PlanOptions = PlanOptions()) -> Plan:
    """Create a conservative plan to move current state toward desired state."""

    changes: List[Change] = []
    changes.extend(_plan_lf_tags(desired, current, options))
    changes.extend(_plan_resource_tags(desired, current, options))
    changes.extend(_plan_grants(desired, current, options))
    return Plan(tuple(changes))


def _plan_lf_tags(desired: DesiredState, current: CurrentState, options: PlanOptions) -> Iterable[Change]:
    current_tags = _lf_tag_index(current.lf_tags)
    for desired_tag in desired.lf_tags:
        current_tag = current_tags.get(desired_tag.key)
        if current_tag is None:
            yield Change(
                action="lf_tag.create",
                target="lf_tag:{}".format(desired_tag.key),
                reason="LF-Tag is missing",
                payload={"tag_key": desired_tag.key, "tag_values": list(desired_tag.values)},
            )
            continue

        desired_values = set(desired_tag.values)
        current_values = set(current_tag.values)
        missing_values = sorted(desired_values - current_values)
        if missing_values:
            yield Change(
                action="lf_tag.add_values",
                target="lf_tag:{}".format(desired_tag.key),
                reason="LF-Tag is missing allowed values",
                payload={"tag_key": desired_tag.key, "tag_values": missing_values},
            )
        extra_values = sorted(current_values - desired_values)
        if extra_values and options.allow_lf_tag_value_removals:
            yield Change(
                action="lf_tag.remove_values",
                target="lf_tag:{}".format(desired_tag.key),
                reason="LF-Tag has values not present in desired state",
                payload={"tag_key": desired_tag.key, "tag_values": extra_values},
                destructive=True,
            )


def _plan_resource_tags(desired: DesiredState, current: CurrentState, options: PlanOptions) -> Iterable[Change]:
    current_by_resource = _resource_tag_index(current.resource_tags)
    desired_by_resource = _resource_tag_index(desired.resource_tags)
    for resource, desired_tags in desired_by_resource.items():
        current_tags = current_by_resource.get(resource, {})
        tags_to_add: Dict[str, List[str]] = {}
        tags_to_remove: Dict[str, List[str]] = {}
        for key, desired_values in desired_tags.items():
            current_values = current_tags.get(key, frozenset())
            missing_values = sorted(desired_values - current_values)
            if missing_values:
                tags_to_add[key] = missing_values
            extra_values = sorted(current_values - desired_values)
            if extra_values and options.allow_resource_tag_removals:
                tags_to_remove[key] = extra_values

        if tags_to_add:
            yield Change(
                action="resource_tag.add_values",
                target=resource.identity,
                reason="Resource is missing desired LF-Tag assignments",
                payload={"resource": resource.to_dict(), "tags": tags_to_add},
            )
        if tags_to_remove:
            yield Change(
                action="resource_tag.remove_values",
                target=resource.identity,
                reason="Resource has LF-Tag assignments not present in desired state",
                payload={"resource": resource.to_dict(), "tags": tags_to_remove},
                destructive=True,
            )


def _plan_grants(desired: DesiredState, current: CurrentState, options: PlanOptions) -> Iterable[Change]:
    desired_grants = _grant_index(desired.grants)
    current_grants = _grant_index(current.grants)

    for identity, desired_grant in desired_grants.items():
        current_grant = current_grants.get(identity)
        current_permissions = set(current_grant.permissions) if current_grant else set()
        current_grantables = set(current_grant.grantable_permissions) if current_grant else set()
        desired_permissions = set(desired_grant.permissions)
        desired_grantables = set(desired_grant.grantable_permissions)

        missing_permissions = sorted(desired_permissions - current_permissions)
        missing_grantables = sorted(desired_grantables - current_grantables)
        if missing_permissions or missing_grantables:
            permissions_to_grant = sorted(set(missing_permissions) | set(missing_grantables))
            yield Change(
                action="grant.add_permissions",
                target=_grant_target(desired_grant),
                reason="Principal is missing desired Lake Formation permissions",
                payload={
                    "principal": desired_grant.principal,
                    "resource": desired_grant.resource.to_dict(),
                    "permissions": permissions_to_grant,
                    "grantable_permissions": missing_grantables,
                },
            )

        extra_permissions = sorted(current_permissions - desired_permissions)
        extra_grantables = sorted(current_grantables - desired_grantables)
        if (extra_permissions or extra_grantables) and options.allow_permission_revokes:
            yield Change(
                action="grant.revoke_permissions",
                target=_grant_target(desired_grant),
                reason="Principal has Lake Formation permissions not present in desired state",
                payload={
                    "principal": desired_grant.principal,
                    "resource": desired_grant.resource.to_dict(),
                    "permissions": extra_permissions,
                    "grantable_permissions": extra_grantables,
                },
                destructive=True,
            )

    if options.allow_permission_revokes:
        for identity, current_grant in current_grants.items():
            if identity in desired_grants:
                continue
            yield Change(
                action="grant.revoke_permissions",
                target=_grant_target(current_grant),
                reason="Principal grant is not present in desired state",
                payload={
                    "principal": current_grant.principal,
                    "resource": current_grant.resource.to_dict(),
                    "permissions": list(current_grant.permissions),
                    "grantable_permissions": list(current_grant.grantable_permissions),
                },
                destructive=True,
            )


def _lf_tag_index(tags: Iterable[LFTagDefinition]) -> Dict[str, LFTagDefinition]:
    merged: Dict[str, set] = {}
    for tag in tags:
        merged.setdefault(tag.key, set()).update(tag.values)
    return {key: LFTagDefinition(key, tuple(values)) for key, values in merged.items()}


def _resource_tag_index(assignments: Iterable[ResourceTagAssignment]) -> Dict[ResourceRef, Dict[str, FrozenSet[str]]]:
    merged: Dict[ResourceRef, Dict[str, set]] = {}
    for assignment in assignments:
        resource_tags = merged.setdefault(assignment.resource, {})
        for key, values in assignment.tags.items():
            resource_tags.setdefault(key, set()).update(values)
    return {
        resource: {key: frozenset(values) for key, values in tags.items()}
        for resource, tags in merged.items()
    }


def _grant_index(grants: Iterable[Grant]) -> Dict[Tuple[str, ResourceRef], Grant]:
    merged: Dict[Tuple[str, ResourceRef], Dict[str, set]] = {}
    for grant in grants:
        entry = merged.setdefault(grant.identity, {"permissions": set(), "grantable_permissions": set()})
        entry["permissions"].update(grant.permissions)
        entry["grantable_permissions"].update(grant.grantable_permissions)
    return {
        identity: Grant(
            principal=identity[0],
            resource=identity[1],
            permissions=tuple(values["permissions"]),
            grantable_permissions=tuple(values["grantable_permissions"]),
        )
        for identity, values in merged.items()
    }


def _grant_target(grant: Grant) -> str:
    return "{} -> {}".format(grant.principal, grant.resource.identity)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_ready(item) for item in value]
    return value
