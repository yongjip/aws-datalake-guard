"""Semantic lint checks for desired Lake Formation guardrail policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

from .models import DesiredState, Grant, ResourceTagAssignment


@dataclass(frozen=True)
class LintFinding:
    """A desired-policy issue that can be detected without AWS access."""

    code: str
    severity: str
    target: str
    message: str
    details: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "target": self.target,
            "message": self.message,
            "details": dict(self.details),
        }


def lint_desired(desired: DesiredState) -> Tuple[LintFinding, ...]:
    """Return semantic desired-policy findings without making AWS calls."""

    findings: List[LintFinding] = []
    if not desired.lf_tags and not desired.resource_tags and not desired.grants:
        findings.append(
            LintFinding(
                code="DESIRED_STATE_EMPTY",
                severity="warning",
                target="desired_state",
                message="Desired state does not define any LF-Tags, resource tag assignments, or grants",
                details={},
            )
        )

    tag_values = {tag.key: set(tag.values) for tag in desired.lf_tags}
    findings.extend(_lint_lf_tag_definitions(tag_values))
    for assignment in desired.resource_tags:
        findings.extend(_lint_resource_tag_assignment(assignment, tag_values))
    for grant in desired.grants:
        findings.extend(_lint_grant(grant, tag_values))
    return tuple(findings)


def _lint_lf_tag_definitions(tag_values: Mapping[str, set]) -> List[LintFinding]:
    findings: List[LintFinding] = []
    for tag_key, values in sorted(tag_values.items()):
        if len(values) > 1000:
            findings.append(
                LintFinding(
                    code="LF_TAG_VALUE_LIMIT_EXCEEDED",
                    severity="error",
                    target="lf_tag:{}".format(tag_key),
                    message="AWS Lake Formation supports at most 1000 values per LF-Tag key",
                    details={"tag_key": tag_key, "value_count": len(values)},
                )
            )
        case_sensitive_values = sorted(_case_sensitive_values((tag_key, *values)))
        if case_sensitive_values:
            findings.append(
                LintFinding(
                    code="LF_TAG_CASE_NORMALIZATION",
                    severity="warning",
                    target="lf_tag:{}".format(tag_key),
                    message="AWS Lake Formation stores LF-Tag keys and values in lower case",
                    details={"values": case_sensitive_values},
                )
            )
    return findings


def _lint_resource_tag_assignment(
    assignment: ResourceTagAssignment,
    tag_values: Mapping[str, set],
) -> List[LintFinding]:
    findings: List[LintFinding] = []
    if len(assignment.tags) > 50:
        findings.append(
            LintFinding(
                code="RESOURCE_TAG_LIMIT_EXCEEDED",
                severity="error",
                target=assignment.resource.identity,
                message="AWS Lake Formation supports at most 50 LF-Tags assigned to a resource",
                details={
                    "resource": assignment.resource.to_dict(),
                    "tag_count": len(assignment.tags),
                },
            )
        )
    for tag_key, values in sorted(assignment.tags.items()):
        if len(values) > 1:
            findings.append(
                LintFinding(
                    code="RESOURCE_TAG_MULTIPLE_VALUES",
                    severity="error",
                    target=assignment.resource.identity,
                    message="AWS Lake Formation allows only one value per LF-Tag key on a resource",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "tag_key": tag_key,
                        "tag_values": sorted(values),
                    },
                )
            )
        case_sensitive_values = sorted(_case_sensitive_values((tag_key, *values)))
        if case_sensitive_values:
            findings.append(
                LintFinding(
                    code="LF_TAG_CASE_NORMALIZATION",
                    severity="warning",
                    target=assignment.resource.identity,
                    message="AWS Lake Formation stores LF-Tag keys and values in lower case",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "values": case_sensitive_values,
                    },
                )
            )
        if tag_key not in tag_values:
            findings.append(
                LintFinding(
                    code="RESOURCE_TAG_KEY_UNDEFINED",
                    severity="error",
                    target=assignment.resource.identity,
                    message="Resource tag assignment references an LF-Tag key that is not defined",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "tag_key": tag_key,
                        "tag_values": sorted(values),
                    },
                )
            )
            continue
        undefined_values = sorted(values - tag_values[tag_key])
        if undefined_values:
            findings.append(
                LintFinding(
                    code="RESOURCE_TAG_VALUE_UNDEFINED",
                    severity="error",
                    target=assignment.resource.identity,
                    message="Resource tag assignment uses LF-Tag values that are not defined",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "tag_key": tag_key,
                        "undefined_values": undefined_values,
                    },
                )
            )
    return findings


def _lint_grant(grant: Grant, tag_values: Mapping[str, set]) -> List[LintFinding]:
    if grant.resource.kind != "lf_tag_policy":
        return []

    findings: List[LintFinding] = []
    if len(grant.resource.expression) > 50:
        findings.append(
            LintFinding(
                code="LF_TAG_POLICY_EXPRESSION_TOO_LARGE",
                severity="error",
                target=_grant_target(grant),
                message="AWS Lake Formation supports at most 50 LF-Tag keys in an expression",
                details={
                    "principal": grant.principal,
                    "resource": grant.resource.to_dict(),
                    "expression_key_count": len(grant.resource.expression),
                },
            )
        )
    for expression_item in grant.resource.expression:
        if len(expression_item.values) > 1000:
            findings.append(
                LintFinding(
                    code="LF_TAG_POLICY_VALUE_LIMIT_EXCEEDED",
                    severity="error",
                    target=_grant_target(grant),
                    message="AWS Lake Formation supports at most 1000 values per LF-Tag key in an expression",
                    details={
                        "principal": grant.principal,
                        "resource": grant.resource.to_dict(),
                        "tag_key": expression_item.key,
                        "value_count": len(expression_item.values),
                    },
                )
            )
        case_sensitive_values = sorted(_case_sensitive_values((expression_item.key, *expression_item.values)))
        if case_sensitive_values:
            findings.append(
                LintFinding(
                    code="LF_TAG_CASE_NORMALIZATION",
                    severity="warning",
                    target=_grant_target(grant),
                    message="AWS Lake Formation stores LF-Tag keys and values in lower case",
                    details={
                        "principal": grant.principal,
                        "resource": grant.resource.to_dict(),
                        "values": case_sensitive_values,
                    },
                )
            )
        if expression_item.key not in tag_values:
            findings.append(
                LintFinding(
                    code="LF_TAG_POLICY_KEY_UNDEFINED",
                    severity="error",
                    target=_grant_target(grant),
                    message="LF-Tag policy expression references an LF-Tag key that is not defined",
                    details={
                        "principal": grant.principal,
                        "resource": grant.resource.to_dict(),
                        "tag_key": expression_item.key,
                        "tag_values": list(expression_item.values),
                    },
                )
            )
            continue
        undefined_values = sorted(
            value for value in set(expression_item.values) - tag_values[expression_item.key] if value != "*"
        )
        if undefined_values:
            findings.append(
                LintFinding(
                    code="LF_TAG_POLICY_VALUE_UNDEFINED",
                    severity="error",
                    target=_grant_target(grant),
                    message="LF-Tag policy expression uses LF-Tag values that are not defined",
                    details={
                        "principal": grant.principal,
                        "resource": grant.resource.to_dict(),
                        "tag_key": expression_item.key,
                        "undefined_values": undefined_values,
                    },
                )
            )
    return findings


def _case_sensitive_values(values: Tuple[str, ...]) -> Tuple[str, ...]:
    return tuple(value for value in values if value != value.lower())


def _grant_target(grant: Grant) -> str:
    return "{} -> {}".format(grant.principal, grant.resource.identity)
