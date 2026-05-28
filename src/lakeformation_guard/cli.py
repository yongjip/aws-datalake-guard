"""Command line interface for lfguard."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Iterable, Optional, Sequence

from ._version import __version__
from .audit import AuditFinding, audit
from .aws import AWSLakeFormationAdapter
from .io import StateFormatError, dumps_json, load_current, load_desired
from .models import CurrentState, DesiredState
from .planner import Plan, PlanOptions, plan


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2
    try:
        if args.command == "plan":
            return _cmd_plan(args)
        if args.command == "audit":
            return _cmd_audit(args)
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

    audit_parser = subparsers.add_parser("audit", help="Report drift between desired and current Lake Formation state.")
    _add_state_args(audit_parser)
    _add_aws_args(audit_parser)
    _add_output_arg(audit_parser)
    audit_parser.add_argument("--fail-on-findings", action="store_true", help="Exit with status 1 when any finding is present.")

    plan_parser = subparsers.add_parser("plan", help="Produce a conservative Lake Formation change plan.")
    _add_state_args(plan_parser)
    _add_aws_args(plan_parser)
    _add_output_arg(plan_parser)
    _add_plan_option_args(plan_parser)

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
