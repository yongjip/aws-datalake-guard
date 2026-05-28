"""Command line interface for lfguard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from ._version import __version__
from .audit import AuditFinding, audit
from .aws import AWSLakeFormationAdapter
from .io import StateFormatError, dumps_json, load_current, load_desired
from .models import CurrentState, DesiredState, GuardrailState
from .planner import Plan, PlanOptions, plan
from .schema import state_json_schema


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2
    try:
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "schema":
            return _cmd_schema(args)
        if args.command == "plan":
            return _cmd_plan(args)
        if args.command == "audit":
            return _cmd_audit(args)
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "snapshot":
            return _cmd_snapshot(args)
        if args.command == "apply":
            return _cmd_apply(args)
    except (StateFormatError, ValueError, RuntimeError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2
    parser.error("unsupported command: {}".format(args.command))
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lfguard",
        description="Audit, plan, and conservatively apply AWS Lake Formation LF-Tag guardrails.",
    )
    parser.add_argument("--version", action="version", version="lfguard {}".format(__version__))
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Generate a starter desired-state policy file.")
    init_parser.add_argument("--output-file", help="Write starter policy JSON to this file instead of stdout.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists.")

    schema_parser = subparsers.add_parser("schema", help="Emit the JSON Schema for desired/current state files.")
    schema_parser.add_argument("--output-file", help="Write schema JSON to this file instead of stdout.")

    audit_parser = subparsers.add_parser("audit", help="Report drift between desired and current Lake Formation state.")
    _add_state_args(audit_parser)
    _add_aws_args(audit_parser)
    _add_output_arg(audit_parser)
    audit_parser.add_argument("--fail-on-findings", action="store_true", help="Exit with status 1 when any finding is present.")

    validate_parser = subparsers.add_parser("validate", help="Validate desired/current state files without AWS access.")
    _add_state_args(validate_parser)
    _add_output_arg(validate_parser)

    plan_parser = subparsers.add_parser("plan", help="Produce a conservative Lake Formation change plan.")
    _add_state_args(plan_parser)
    _add_aws_args(plan_parser)
    _add_output_arg(plan_parser)
    _add_plan_option_args(plan_parser)

    snapshot_parser = subparsers.add_parser("snapshot", help="Export live AWS state for a desired policy scope.")
    snapshot_parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file that defines the snapshot scope.")
    _add_aws_args(snapshot_parser)
    snapshot_parser.add_argument("--output-file", help="Write snapshot JSON to this file instead of stdout.")

    apply_parser = subparsers.add_parser("apply", help="Dry-run or execute a Lake Formation change plan.")
    _add_state_args(apply_parser)
    _add_aws_args(apply_parser)
    _add_output_arg(apply_parser)
    _add_plan_option_args(apply_parser)
    apply_parser.add_argument("--execute", action="store_true", help="Apply the computed plan. Defaults to dry-run.")

    return parser


def _cmd_audit(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _load_current(args, desired)
    findings = audit(desired, current)
    _print_findings(findings, args.output)
    if findings and args.fail_on_findings:
        return 1
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _load_current(args, desired)
    change_plan = plan(desired, current, _plan_options(args))
    _print_plan(change_plan, args.output)
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    text = dumps_json(_starter_desired_state())
    if args.output_file:
        output_path = Path(args.output_file)
        if output_path.exists() and not args.force:
            raise RuntimeError("{} already exists; pass --force to overwrite it".format(output_path))
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("Could not write starter policy to {}: {}".format(output_path, exc)) from exc
    else:
        print(text, end="")
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    text = dumps_json(state_json_schema())
    if args.output_file:
        output_path = Path(args.output_file)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("Could not write schema to {}: {}".format(output_path, exc)) from exc
    else:
        print(text, end="")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = load_current(args.current_snapshot) if args.current_snapshot else None
    desired_summary = _state_summary(desired)
    current_summary = _state_summary(current) if current else None
    if args.output == "json":
        payload: Any = {"desired": {"valid": True, **desired_summary}}
        if current_summary:
            payload["current_snapshot"] = {"valid": True, **current_summary}
        print(dumps_json(payload), end="")
        return 0
    print(_format_validation_summary("Desired state is valid", desired_summary))
    if current_summary:
        print(_format_validation_summary("Current snapshot is valid", current_summary))
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _aws_adapter(args).load_current_state_for(desired)
    text = dumps_json(current.to_dict())
    if args.output_file:
        output_path = Path(args.output_file)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("Could not write snapshot to {}: {}".format(output_path, exc)) from exc
    else:
        print(text, end="")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _load_current(args, desired)
    change_plan = plan(desired, current, _plan_options(args))
    if not args.execute:
        _print_plan(change_plan, args.output, prefix="Dry run: no changes applied.")
        return 0

    adapter = _aws_adapter(args)
    results = adapter.apply(
        change_plan,
        dry_run=False,
        allow_destructive=_has_destructive_allowance(args),
    )
    if args.output == "json":
        print(dumps_json({"plan": change_plan.to_dict(), "results": [result.to_dict() for result in results]}), end="")
    else:
        print("Applied {} change(s).".format(sum(1 for result in results if result.applied)))
        _print_plan(change_plan, args.output)
    return 0


def _add_state_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file.")
    parser.add_argument(
        "--current-snapshot",
        help="Current state JSON/YAML snapshot. When omitted, live AWS state is loaded with boto3.",
    )


def _add_aws_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", help="AWS profile for live state/apply.")
    parser.add_argument("--region", help="AWS region for live state/apply.")
    parser.add_argument("--catalog-id", help="AWS Glue Data Catalog ID.")


def _add_output_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", choices=("text", "json"), default="text", help="Output format.")


def _add_plan_option_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-lf-tag-value-removals", action="store_true", help="Plan LF-Tag value removals.")
    parser.add_argument("--allow-resource-tag-removals", action="store_true", help="Plan LF-Tag assignment removals.")
    parser.add_argument("--allow-permission-revokes", action="store_true", help="Plan Lake Formation permission revokes.")


def _load_current(args: argparse.Namespace, desired: DesiredState) -> CurrentState:
    if args.current_snapshot:
        return load_current(args.current_snapshot)
    return _aws_adapter(args).load_current_state_for(desired)


def _aws_adapter(args: argparse.Namespace) -> AWSLakeFormationAdapter:
    return AWSLakeFormationAdapter.from_boto3(
        profile_name=args.profile,
        region_name=args.region,
        catalog_id=args.catalog_id,
    )


def _plan_options(args: argparse.Namespace) -> PlanOptions:
    return PlanOptions(
        allow_lf_tag_value_removals=args.allow_lf_tag_value_removals,
        allow_resource_tag_removals=args.allow_resource_tag_removals,
        allow_permission_revokes=args.allow_permission_revokes,
    )


def _has_destructive_allowance(args: argparse.Namespace) -> bool:
    return bool(
        args.allow_lf_tag_value_removals
        or args.allow_resource_tag_removals
        or args.allow_permission_revokes
    )


def _state_summary(state: GuardrailState) -> dict:
    return {
        "lf_tags": len(state.lf_tags),
        "resource_tags": len(state.resource_tags),
        "grants": len(state.grants),
    }


def _format_validation_summary(prefix: str, summary: dict) -> str:
    return (
        "{prefix}: {lf_tags} LF-Tag definition(s), "
        "{resource_tags} resource tag assignment(s), {grants} grant(s)."
    ).format(prefix=prefix, **summary)


def _starter_desired_state() -> dict:
    return {
        "lf_tags": {
            "domain": ["analytics"],
            "sensitivity": ["public", "internal", "restricted"],
        },
        "resource_tags": [
            {
                "resource": {
                    "kind": "table",
                    "database": "analytics",
                    "table": "orders",
                },
                "tags": {
                    "domain": ["analytics"],
                    "sensitivity": ["internal"],
                },
            }
        ],
        "grants": [
            {
                "principal": "arn:aws:iam::111122223333:role/Analyst",
                "resource": {
                    "kind": "lf_tag_policy",
                    "resource_type": "TABLE",
                    "expression": {
                        "domain": ["analytics"],
                        "sensitivity": ["public", "internal"],
                    },
                },
                "permissions": ["DESCRIBE", "SELECT"],
            }
        ],
    }


def _print_plan(change_plan: Plan, output: str, *, prefix: Optional[str] = None) -> None:
    if output == "json":
        data: Any = change_plan.to_dict()
        if prefix:
            data = {"message": prefix, "plan": data}
        print(dumps_json(data), end="")
        return
    if prefix:
        print(prefix)
    summary = change_plan.summary()
    print(
        "Plan: {total} change(s), {safe} safe, {destructive} destructive.".format(
            **summary
        )
    )
    if not change_plan.changes:
        return
    for change in change_plan.changes:
        marker = "destructive" if change.destructive else "safe"
        print("- [{marker}] {action} {target}: {reason}".format(
            marker=marker,
            action=change.action,
            target=change.target,
            reason=change.reason,
        ))


def _print_findings(findings: Iterable[AuditFinding], output: str) -> None:
    findings = tuple(findings)
    if output == "json":
        print(dumps_json({"findings": [finding.to_dict() for finding in findings]}), end="")
        return
    if not findings:
        print("No findings.")
        return
    print("Findings: {}.".format(len(findings)))
    for finding in findings:
        print("- [{severity}] {code} {target}: {message}".format(
            severity=finding.severity,
            code=finding.code,
            target=finding.target,
            message=finding.message,
        ))
