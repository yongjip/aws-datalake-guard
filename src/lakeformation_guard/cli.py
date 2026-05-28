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
        if args.command == "sample":
            return _cmd_sample(args)
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
    init_parser.add_argument(
        "--template",
        choices=("data-domain", "blank"),
        default="data-domain",
        help="Starter policy template. Defaults to data-domain.",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists.")

    sample_parser = subparsers.add_parser("sample", help="Generate offline demo desired/current state files.")
    sample_parser.add_argument("--output-dir", required=True, help="Directory to write sample files into.")
    sample_parser.add_argument(
        "--format",
        choices=("json", "yaml", "both"),
        default="json",
        help="Sample state file format. Defaults to json.",
    )
    sample_parser.add_argument("--force", action="store_true", help="Overwrite sample files if they already exist.")

    schema_parser = subparsers.add_parser("schema", help="Emit the JSON Schema for desired/current state files.")
    schema_parser.add_argument("--output-file", help="Write schema JSON to this file instead of stdout.")

    doctor_parser = subparsers.add_parser("doctor", help="Check local lfguard install and optional integrations.")
    _add_output_arg(doctor_parser)
    _add_report_output_file_arg(doctor_parser)
    doctor_parser.add_argument(
        "--require",
        action="append",
        choices=("aws", "yaml"),
        default=[],
        help="Fail when the named optional extra is not installed. Repeat for multiple extras.",
    )

    audit_parser = subparsers.add_parser("audit", help="Report drift between desired and current Lake Formation state.")
    _add_state_args(audit_parser)
    _add_aws_args(audit_parser)
    _add_output_arg(audit_parser, markdown=True, sarif=True)
    _add_report_output_file_arg(audit_parser)
    _add_github_summary_arg(audit_parser)
    audit_parser.add_argument("--fail-on-findings", action="store_true", help="Exit with status 1 when any finding is present.")
    audit_parser.add_argument(
        "--fail-on-severity",
        choices=("any", "error"),
        default="any",
        help="Finding severity that triggers --fail-on-findings. Defaults to any finding.",
    )

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
    _emit_output(_render_findings(findings, args.output, sarif_uri=args.desired), args.output_file, label="audit report")
    if args.fail_on_findings and _should_fail_on_findings(findings, args.fail_on_severity):
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
    text = _dump_starter_desired_state(output_format, args.template)
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


def _cmd_sample(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    files = _sample_files(args.format)
    existing = [output_dir / name for name in files if (output_dir / name).exists()]
    if existing and not args.force:
        raise RuntimeError(
            "{} already exists; pass --force to overwrite sample files".format(
                ", ".join(str(path) for path in existing)
            )
        )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (output_dir / name).write_text(text, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Could not write sample files to {}: {}".format(output_dir, exc)) from exc

    print("Wrote lfguard sample files to {}.\n".format(output_dir))
    print("Run:")
    desired_name, current_name = _sample_primary_files(args.format)
    print("  lfguard plan --desired {}/{} --current-snapshot {}/{}".format(output_dir, desired_name, output_dir, current_name))
    print("\nSee {}/README.md for more commands.".format(output_dir))
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
    report = _doctor_report(required_extras=args.require)
    _emit_output(_render_doctor(report, args.output), args.output_file, label="doctor report")
    if report["missing_required_extras"]:
        return 1
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


def _add_output_arg(parser: argparse.ArgumentParser, *, markdown: bool = False, sarif: bool = False) -> None:
    choices = ["text", "json"]
    if markdown:
        choices.append("markdown")
    if sarif:
        choices.append("sarif")
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


def _dump_starter_desired_state(output_format: str, template: str = "data-domain") -> str:
    data = _starter_desired_state(template)
    if output_format == "yaml":
        return dumps_yaml(data)
    return dumps_json(data)


def _doctor_report(required_extras: Optional[Iterable[str]] = None) -> dict:
    report = {
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
    required = tuple(sorted(set(required_extras or ())))
    report["required_extras"] = list(required)
    report["missing_required_extras"] = [
        extra for extra in required if not _optional_extra_installed(report, extra)
    ]
    return report


def _optional_extra_installed(report: dict, extra: str) -> bool:
    for status in report["optional_dependencies"].values():
        if status["extra"] == extra:
            return bool(status["installed"])
    return False


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
    if report["required_extras"]:
        lines.append("Required extras:")
        for extra in report["required_extras"]:
            state = "missing" if extra in report["missing_required_extras"] else "installed"
            lines.append("- {}: {}".format(extra, state))
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


def _starter_desired_state(template: str = "data-domain") -> dict:
    if template == "blank":
        return {
            "lf_tags": {},
            "resource_tags": [],
            "grants": [],
        }
    if template != "data-domain":
        raise ValueError("unsupported starter template: {}".format(template))
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


def _sample_desired_state() -> dict:
    return {
        "lf_tags": {
            "sensitivity": ["public", "internal", "restricted"],
            "domain": ["sales", "finance"],
        },
        "resource_tags": [
            {
                "resource": {
                    "kind": "table",
                    "database": "analytics",
                    "table": "orders",
                },
                "tags": {
                    "sensitivity": ["internal"],
                    "domain": ["sales"],
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
                        "domain": ["sales"],
                        "sensitivity": ["public", "internal"],
                    },
                },
                "permissions": ["SELECT", "DESCRIBE"],
            }
        ],
    }


def _sample_current_state() -> dict:
    return {
        "lf_tags": {
            "sensitivity": ["public"],
            "domain": ["sales", "finance"],
        },
        "resource_tags": [
            {
                "resource": {
                    "kind": "table",
                    "database": "analytics",
                    "table": "orders",
                },
                "tags": {
                    "domain": ["sales"],
                },
            }
        ],
        "grants": [],
    }


def _sample_files(output_format: str) -> dict:
    desired = _sample_desired_state()
    current = _sample_current_state()
    files = {}
    if output_format in {"json", "both"}:
        files["desired.json"] = dumps_json(desired)
        files["current-snapshot.json"] = dumps_json(current)
    if output_format in {"yaml", "both"}:
        files["desired.yaml"] = dumps_yaml(desired)
        files["current-snapshot.yaml"] = dumps_yaml(current)
    desired_name, current_name = _sample_primary_files(output_format)
    files["README.md"] = _sample_readme(
        desired_name,
        current_name,
        include_yaml_note=output_format in {"yaml", "both"},
        include_both_note=output_format == "both",
    )
    return files


def _sample_primary_files(output_format: str) -> tuple:
    if output_format == "yaml":
        return "desired.yaml", "current-snapshot.yaml"
    return "desired.json", "current-snapshot.json"


def _sample_readme(
    desired_name: str,
    current_name: str,
    *,
    include_yaml_note: bool = False,
    include_both_note: bool = False,
) -> str:
    yaml_note = ""
    if include_yaml_note:
        yaml_note = """## YAML Support

YAML state files require the optional YAML extra when you read them:

```bash
python -m pip install "lfguard[yaml]"
```

"""
    both_note = ""
    if include_both_note:
        both_note = """This directory includes both JSON and YAML state files. The JSON commands work
with the base `lfguard` install.

"""
    return """# lfguard Demo

This directory contains a desired Lake Formation guardrail policy and a
deliberately incomplete current-state snapshot. It is safe to use without AWS
credentials.

{both_note}{yaml_note}
## Validate

```bash
lfguard validate --desired {desired_name} --current-snapshot {current_name}
```

## Audit Drift

```bash
lfguard audit --desired {desired_name} --current-snapshot {current_name}
```

## Plan Safe Changes

```bash
lfguard plan --desired {desired_name} --current-snapshot {current_name}
```

Expected summary:

```text
Plan: 3 change(s), 3 safe, 0 destructive.
```

## Save Reports

```bash
lfguard audit \\
  --desired {desired_name} \\
  --current-snapshot {current_name} \\
  --output json \\
  --output-file lfguard-audit.json

lfguard plan \\
  --desired {desired_name} \\
  --current-snapshot {current_name} \\
  --output markdown \\
  --output-file lfguard-plan.md
```
""".format(
        both_note=both_note,
        current_name=current_name,
        desired_name=desired_name,
        yaml_note=yaml_note,
    )


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


def _render_findings(findings: Iterable[AuditFinding], output: str, *, sarif_uri: Optional[str] = None) -> str:
    findings = tuple(findings)
    summary = _finding_summary(findings)
    if output == "json":
        return dumps_json(
            {
                "summary": summary,
                "findings": [finding.to_dict() for finding in findings],
            }
        )
    if output == "sarif":
        return dumps_json(_findings_to_sarif(findings, sarif_uri=sarif_uri))
    if output == "markdown":
        return _render_findings_markdown(findings)
    lines = []
    if not findings:
        return "No findings.\n"
    lines.append(_format_finding_summary(summary))
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
    summary = _finding_summary(findings)
    lines = ["### lfguard audit", ""]
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "- Total findings: {total}".format(**summary),
            "- Error findings: {errors}".format(**summary),
            "- Warning findings: {warnings}".format(**summary),
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


def _findings_to_sarif(findings: Iterable[AuditFinding], *, sarif_uri: Optional[str] = None) -> dict:
    findings = tuple(findings)
    rules = []
    for code in sorted({finding.code for finding in findings}):
        rule_findings = [finding for finding in findings if finding.code == code]
        severity = "error" if any(finding.severity == "error" for finding in rule_findings) else "warning"
        rules.append(
            {
                "id": code,
                "name": code,
                "shortDescription": {"text": rule_findings[0].message},
                "defaultConfiguration": {"level": _sarif_level(severity)},
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "lfguard",
                        "version": __version__,
                        "informationUri": "https://github.com/yongjip/aws-datalake-guard",
                        "rules": rules,
                    }
                },
                "results": [
                    {
                        "ruleId": finding.code,
                        "level": _sarif_level(finding.severity),
                        "message": {"text": "{}: {}".format(finding.target, finding.message)},
                        "locations": [_sarif_location(finding, sarif_uri)],
                        "properties": {
                            "severity": finding.severity,
                            "target": finding.target,
                            "details": dict(finding.details),
                        },
                    }
                    for finding in findings
                ],
            }
        ],
    }


def _sarif_level(severity: str) -> str:
    if severity == "error":
        return "error"
    if severity == "warning":
        return "warning"
    return "note"


def _sarif_location(finding: AuditFinding, sarif_uri: Optional[str]) -> dict:
    artifact_uri = sarif_uri or "lfguard-audit"
    return {
        "physicalLocation": {
            "artifactLocation": {"uri": artifact_uri},
            "region": {"snippet": {"text": finding.target}},
        },
        "logicalLocations": [{"fullyQualifiedName": finding.target}],
    }


def _finding_summary(findings: Iterable[AuditFinding]) -> dict:
    findings = tuple(findings)
    return {
        "total": len(findings),
        "errors": sum(1 for finding in findings if finding.severity == "error"),
        "warnings": sum(1 for finding in findings if finding.severity == "warning"),
    }


def _format_finding_summary(summary: dict) -> str:
    return "Findings: {total} total, {errors} error(s), {warnings} warning(s).".format(**summary)


def _should_fail_on_findings(findings: Iterable[AuditFinding], fail_on_severity: str) -> bool:
    findings = tuple(findings)
    if fail_on_severity == "error":
        return any(finding.severity == "error" for finding in findings)
    return bool(findings)


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
