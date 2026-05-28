"""Command line interface for lfguard."""

from __future__ import annotations

import argparse
import os
import platform
import sys
from importlib import metadata, util
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from ._version import __version__
from .audit import AuditFinding, audit
from .aws import AWSLakeFormationAdapter
from .io import StateFormatError, dumps_json, dumps_yaml, load_current, load_desired
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
        if args.command == "doctor":
            return _cmd_doctor(args)
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
    init_parser.add_argument("--output-file", help="Write starter policy to this file instead of stdout.")
    init_parser.add_argument(
        "--format",
        choices=("json", "yaml"),
        help="Starter policy output format. Defaults to the output file extension, or json for stdout.",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists.")

    schema_parser = subparsers.add_parser("schema", help="Emit the JSON Schema for desired/current state files.")
    schema_parser.add_argument("--output-file", help="Write schema JSON to this file instead of stdout.")

    doctor_parser = subparsers.add_parser("doctor", help="Check local lfguard install and optional integrations.")
    _add_output_arg(doctor_parser)
    _add_report_output_file_arg(doctor_parser)

    audit_parser = subparsers.add_parser("audit", help="Report drift between desired and current Lake Formation state.")
    _add_state_args(audit_parser)
    _add_aws_args(audit_parser)
    _add_output_arg(audit_parser, markdown=True)
    _add_report_output_file_arg(audit_parser)
    _add_github_summary_arg(audit_parser)
    audit_parser.add_argument("--fail-on-findings", action="store_true", help="Exit with status 1 when any finding is present.")

    validate_parser = subparsers.add_parser("validate", help="Validate desired/current state files without AWS access.")
    _add_state_args(validate_parser)
    _add_output_arg(validate_parser)
    _add_report_output_file_arg(validate_parser)

    plan_parser = subparsers.add_parser("plan", help="Produce a conservative Lake Formation change plan.")
    _add_state_args(plan_parser)
    _add_aws_args(plan_parser)
    _add_output_arg(plan_parser, markdown=True)
    _add_report_output_file_arg(plan_parser)
    _add_github_summary_arg(plan_parser)
    _add_plan_option_args(plan_parser)
    plan_parser.add_argument("--fail-on-changes", action="store_true", help="Exit with status 1 when the plan contains any change.")

    snapshot_parser = subparsers.add_parser("snapshot", help="Export live AWS state for a desired policy scope.")
    snapshot_parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file that defines the snapshot scope.")
    _add_aws_args(snapshot_parser)
    snapshot_parser.add_argument("--output-file", help="Write snapshot JSON to this file instead of stdout.")

    apply_parser = subparsers.add_parser("apply", help="Dry-run or execute a Lake Formation change plan.")
    _add_state_args(apply_parser)
    _add_aws_args(apply_parser)
    _add_output_arg(apply_parser, markdown=True)
    _add_report_output_file_arg(apply_parser)
    _add_github_summary_arg(apply_parser)
    _add_plan_option_args(apply_parser)
    apply_parser.add_argument("--execute", action="store_true", help="Apply the computed plan. Defaults to dry-run.")

    return parser


def _cmd_audit(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _load_current(args, desired)
    findings = audit(desired, current)
    if args.github_summary:
        _append_github_summary(_render_findings_markdown(findings))
    _emit_output(_render_findings(findings, args.output), args.output_file, label="audit report")
    if findings and args.fail_on_findings:
        return 1
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _load_current(args, desired)
    change_plan = plan(desired, current, _plan_options(args))
    if args.github_summary:
        _append_github_summary(_render_plan_markdown(change_plan))
    _emit_output(_render_plan(change_plan, args.output), args.output_file, label="plan report")
    if change_plan.changes and args.fail_on_changes:
        return 1
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    output_format = _resolve_init_format(args.format, args.output_file)
    text = _dump_starter_desired_state(output_format)
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


def _cmd_doctor(args: argparse.Namespace) -> int:
    report = _doctor_report()
    _emit_output(_render_doctor(report, args.output), args.output_file, label="doctor report")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = load_current(args.current_snapshot) if args.current_snapshot else None
    desired_summary = _state_summary(desired)
    current_summary = _state_summary(current) if current else None
    _emit_output(
        _render_validation(desired_summary, current_summary, args.output),
        args.output_file,
        label="validation report",
    )
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
        if args.github_summary:
            _append_github_summary(_render_plan_markdown(change_plan, prefix="Dry run: no changes applied."))
        _emit_output(
            _render_plan(change_plan, args.output, prefix="Dry run: no changes applied."),
            args.output_file,
            label="apply report",
        )
        return 0

    adapter = _aws_adapter(args)
    results = adapter.apply(
        change_plan,
        dry_run=False,
        allow_destructive=_has_destructive_allowance(args),
    )
    applied_count = sum(1 for result in results if result.applied)
    if args.github_summary:
        _append_github_summary(_render_plan_markdown(change_plan, prefix="Applied {} change(s).".format(applied_count)))
    _emit_output(
        _render_apply(change_plan, results, args.output, applied_count=applied_count),
        args.output_file,
        label="apply report",
    )
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


def _add_output_arg(parser: argparse.ArgumentParser, *, markdown: bool = False) -> None:
    choices = ("text", "json", "markdown") if markdown else ("text", "json")
    parser.add_argument("--output", choices=choices, default="text", help="Output format.")


def _add_report_output_file_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-file", help="Write command output to this file instead of stdout.")


def _add_github_summary_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--github-summary",
        action="store_true",
        help="Append a Markdown report to $GITHUB_STEP_SUMMARY.",
    )


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


def _resolve_init_format(requested_format: Optional[str], output_file: Optional[str]) -> str:
    if requested_format:
        return requested_format
    if output_file and Path(output_file).suffix.lower() in {".yaml", ".yml"}:
        return "yaml"
    return "json"


def _dump_starter_desired_state(output_format: str) -> str:
    data = _starter_desired_state()
    if output_format == "yaml":
        return dumps_yaml(data)
    return dumps_json(data)


def _doctor_report() -> dict:
    return {
        "version": __version__,
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "optional_dependencies": {
            "boto3": _dependency_status(
                "boto3",
                "boto3",
                extra="aws",
                purpose="live AWS snapshot and apply workflows",
            ),
            "PyYAML": _dependency_status(
                "yaml",
                "PyYAML",
                extra="yaml",
                purpose="YAML desired/current state files",
            ),
        },
        "aws_environment": {
            "profile": os.environ.get("AWS_PROFILE"),
            "region": os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
            "catalog_id": os.environ.get("LF_GUARD_CATALOG_ID"),
        },
        "aws_calls_made": False,
    }


def _dependency_status(module_name: str, distribution_name: str, *, extra: str, purpose: str) -> dict:
    installed = util.find_spec(module_name) is not None
    version = None
    if installed:
        try:
            version = metadata.version(distribution_name)
        except metadata.PackageNotFoundError:
            version = None
    return {
        "installed": installed,
        "version": version,
        "extra": extra,
        "purpose": purpose,
    }


def _print_doctor(report: dict) -> None:
    print(_render_doctor(report, "text"), end="")


def _render_doctor(report: dict, output: str) -> str:
    if output == "json":
        return dumps_json(report)
    lines = [
        "lfguard: {}".format(report["version"]),
        "Python: {version} ({executable})".format(**report["python"]),
        "Optional dependencies:",
    ]
    for name, status in report["optional_dependencies"].items():
        if status["installed"]:
            suffix = " {}".format(status["version"]) if status["version"] else ""
            lines.append("- {}: installed{} ({})".format(name, suffix, status["purpose"]))
        else:
            lines.append("- {}: missing; install lfguard[{}] for {}".format(name, status["extra"], status["purpose"]))
    lines.append("AWS environment:")
    aws_env = report["aws_environment"]
    lines.append("- profile: {}".format(aws_env["profile"] or "not set"))
    lines.append("- region: {}".format(aws_env["region"] or "not set"))
    lines.append("- catalog_id: {}".format(aws_env["catalog_id"] or "not set"))
    lines.append("No AWS calls were made.")
    return "\n".join(lines) + "\n"


def _render_validation(desired_summary: dict, current_summary: Optional[dict], output: str) -> str:
    if output == "json":
        payload: Any = {"desired": {"valid": True, **desired_summary}}
        if current_summary:
            payload["current_snapshot"] = {"valid": True, **current_summary}
        return dumps_json(payload)
    lines = [_format_validation_summary("Desired state is valid", desired_summary)]
    if current_summary:
        lines.append(_format_validation_summary("Current snapshot is valid", current_summary))
    return "\n".join(lines) + "\n"


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
    print(_render_plan(change_plan, output, prefix=prefix), end="")


def _render_plan(change_plan: Plan, output: str, *, prefix: Optional[str] = None) -> str:
    if output == "json":
        data: Any = change_plan.to_dict()
        if prefix:
            data = {"message": prefix, "plan": data}
        return dumps_json(data)
    if output == "markdown":
        return _render_plan_markdown(change_plan, prefix=prefix)
    lines = []
    if prefix:
        lines.append(prefix)
    summary = change_plan.summary()
    lines.append(
        "Plan: {total} change(s), {safe} safe, {destructive} destructive.".format(
            **summary
        )
    )
    if not change_plan.changes:
        return "\n".join(lines) + "\n"
    for change in change_plan.changes:
        marker = "destructive" if change.destructive else "safe"
        lines.append(
            "- [{marker}] {action} {target}: {reason}".format(
                marker=marker,
                action=change.action,
                target=change.target,
                reason=change.reason,
            )
        )
    return "\n".join(lines) + "\n"


def _print_plan_markdown(change_plan: Plan, *, prefix: Optional[str] = None) -> None:
    print(_render_plan_markdown(change_plan, prefix=prefix), end="")


def _render_plan_markdown(change_plan: Plan, *, prefix: Optional[str] = None) -> str:
    lines = []
    if prefix:
        lines.extend([prefix, ""])
    summary = change_plan.summary()
    lines.extend(
        [
            "### lfguard plan",
            "",
            "- Total changes: {total}".format(**summary),
            "- Safe changes: {safe}".format(**summary),
            "- Destructive changes: {destructive}".format(**summary),
        ]
    )
    if not change_plan.changes:
        lines.extend(["", "No changes."])
        return "\n".join(lines) + "\n"
    lines.extend(["", "| Safety | Action | Target | Reason |", "| --- | --- | --- | --- |"])
    for change in change_plan.changes:
        marker = "destructive" if change.destructive else "safe"
        lines.append(
            "| {safety} | {action} | {target} | {reason} |".format(
                safety=_markdown_cell(marker),
                action=_markdown_cell(change.action),
                target=_markdown_cell(change.target),
                reason=_markdown_cell(change.reason),
            )
        )
    return "\n".join(lines) + "\n"


def _render_apply(change_plan: Plan, results: Iterable[Any], output: str, *, applied_count: int) -> str:
    if output == "json":
        return dumps_json({"plan": change_plan.to_dict(), "results": [result.to_dict() for result in results]})
    return _render_plan(change_plan, output, prefix="Applied {} change(s).".format(applied_count))


def _print_findings(findings: Iterable[AuditFinding], output: str) -> None:
    print(_render_findings(findings, output), end="")


def _render_findings(findings: Iterable[AuditFinding], output: str) -> str:
    findings = tuple(findings)
    if output == "json":
        return dumps_json({"findings": [finding.to_dict() for finding in findings]})
    if output == "markdown":
        return _render_findings_markdown(findings)
    lines = []
    if not findings:
        return "No findings.\n"
    lines.append("Findings: {}.".format(len(findings)))
    for finding in findings:
        lines.append(
            "- [{severity}] {code} {target}: {message}".format(
                severity=finding.severity,
                code=finding.code,
                target=finding.target,
                message=finding.message,
            )
        )
    return "\n".join(lines) + "\n"


def _print_findings_markdown(findings: Iterable[AuditFinding]) -> None:
    print(_render_findings_markdown(findings), end="")


def _render_findings_markdown(findings: Iterable[AuditFinding]) -> str:
    findings = tuple(findings)
    lines = ["### lfguard audit", ""]
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "Findings: {}.".format(len(findings)),
            "",
            "| Severity | Code | Target | Message |",
            "| --- | --- | --- | --- |",
        ]
    )
    for finding in findings:
        lines.append(
            "| {severity} | {code} | {target} | {message} |".format(
                severity=_markdown_cell(finding.severity),
                code=_markdown_cell(finding.code),
                target=_markdown_cell(finding.target),
                message=_markdown_cell(finding.message),
            )
        )
    return "\n".join(lines) + "\n"


def _emit_output(text: str, output_file: Optional[str], *, label: str) -> None:
    if output_file:
        _write_text_file(Path(output_file), text, label)
        return
    print(text, end="")


def _write_text_file(output_path: Path, text: str, label: str) -> None:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Could not write {} to {}: {}".format(label, output_path, exc)) from exc


def _append_github_summary(markdown_text: str) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        raise RuntimeError("GITHUB_STEP_SUMMARY is not set; use --output markdown or run inside GitHub Actions")
    try:
        with Path(summary_file).open("a", encoding="utf-8") as handle:
            handle.write(markdown_text)
            if not markdown_text.endswith("\n"):
                handle.write("\n")
            handle.write("\n")
    except OSError as exc:
        raise RuntimeError("Could not write GitHub summary to {}: {}".format(summary_file, exc)) from exc


def _markdown_cell(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")
