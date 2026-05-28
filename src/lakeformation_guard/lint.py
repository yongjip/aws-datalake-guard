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
    for assignment in desired.resource_tags:
        findings.extend(_lint_resource_tag_assignment(assignment, tag_values))
    for grant in desired.grants:
        findings.extend(_lint_grant(grant, tag_values))
    return tuple(findings)


def _lint_resource_tag_assignment(
    assignment: ResourceTagAssignment,
    tag_values: Mapping[str, set],
) -> List[LintFinding]:
    findings: List[LintFinding] = []
    for tag_key, values in sorted(assignment.tags.items()):
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
    for expression_item in grant.resource.expression:
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
        undefined_values = sorted(set(expression_item.values) - tag_values[expression_item.key])
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


def _grant_target(grant: Grant) -> str:
    return "{} -> {}".format(grant.principal, grant.resource.identity)
