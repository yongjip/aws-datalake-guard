import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lakeformation_guard import CurrentState, DesiredState, __version__, audit
from lakeformation_guard.aws import ApplyResult
from lakeformation_guard.cli import main


class AuditCliTests(unittest.TestCase):
    def test_audit_reports_missing_and_unmanaged_drift(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    }
                ],
            }
        )
        current = CurrentState.from_dict(
            {
                "lf_tags": {"sensitivity": ["restricted"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DROP"],
                    }
                ],
            }
        )

        findings = audit(desired, current)

        self.assertEqual(
            {finding.code for finding in findings},
            {
                "LF_TAG_VALUES_MISSING",
                "LF_TAG_VALUES_UNMANAGED",
                "GRANT_PERMISSIONS_MISSING",
                "GRANT_PERMISSIONS_UNMANAGED",
            },
        )

    def test_cli_plan_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "database", "database": "analytics"},
                                "permissions": ["DESCRIBE"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["summary"], {"total": 2, "safe": 2, "destructive": 0})
            self.assertEqual(
                [change["action"] for change in payload["changes"]],
                ["lf_tag.create", "grant.add_permissions"],
            )

    def test_cli_plan_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "database", "database": "analytics"},
                                "permissions": ["DESCRIBE"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard plan", stdout.getvalue())
            self.assertIn("| Safety | Action | Target | Reason |", stdout.getvalue())
            self.assertIn("| safe | lf_tag.create | lf_tag:sensitivity | LF-Tag is missing |", stdout.getvalue())

    def test_cli_plan_can_fail_when_changes_are_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--fail-on-changes",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("Plan: 1 change(s), 1 safe, 0 destructive.", stdout.getvalue())

    def test_cli_plan_writes_report_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "lfguard-plan.md"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "markdown",
                        "--output-file",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("### lfguard plan", report)
            self.assertIn("| safe | lf_tag.create | lf_tag:sensitivity | LF-Tag is missing |", report)

    def test_cli_plan_writes_json_report_before_failing_on_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "plan.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                        "--output-file",
                        str(output_path),
                        "--fail-on-changes",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"], {"total": 1, "safe": 1, "destructive": 0})

    def test_cli_plan_fail_on_changes_passes_when_plan_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            state = {"lf_tags": {"sensitivity": ["internal"]}, "grants": []}
            desired_path.write_text(json.dumps(state), encoding="utf-8")
            current_path.write_text(json.dumps(state), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--fail-on-changes",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Plan: 0 change(s), 0 safe, 0 destructive.", stdout.getvalue())

    def test_cli_audit_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "database", "database": "analytics"},
                                "permissions": ["DESCRIBE"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard audit", stdout.getvalue())
            self.assertIn("- Total findings: 3", stdout.getvalue())
            self.assertIn("- Error findings: 2", stdout.getvalue())
            self.assertIn("- Warning findings: 1", stdout.getvalue())
            self.assertIn("| Severity | Code | Target | Message |", stdout.getvalue())
            self.assertIn("LF_TAG_VALUES_MISSING", stdout.getvalue())

    def test_cli_audit_outputs_json_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["summary"], {"total": 2, "errors": 1, "warnings": 1})
            self.assertEqual(
                [finding["code"] for finding in payload["findings"]],
                ["LF_TAG_VALUES_MISSING", "LF_TAG_VALUES_UNMANAGED"],
            )

    def test_cli_audit_writes_report_output_file_before_failing_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "lfguard-audit.txt"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output-file",
                        str(output_path),
                        "--fail-on-findings",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("Findings: 2 total, 1 error(s), 1 warning(s).", report)
            self.assertIn("LF_TAG_VALUES_MISSING", report)

    def test_cli_audit_default_fail_on_findings_fails_for_warning_only_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal", "restricted"]}, "grants": []}),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--fail-on-findings",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("[warning] LF_TAG_VALUES_UNMANAGED", stdout.getvalue())

    def test_cli_audit_can_fail_on_error_severity_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal", "restricted"]}, "grants": []}),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--fail-on-findings",
                        "--fail-on-severity",
                        "error",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("[warning] LF_TAG_VALUES_UNMANAGED", stdout.getvalue())

    def test_cli_audit_writes_github_summary_before_failing_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            summary_path = tmp_path / "summary.md"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "audit",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--fail-on-findings",
                            "--github-summary",
                        ]
                    )

            self.assertEqual(exit_code, 1)
            self.assertIn("Findings:", stdout.getvalue())
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("### lfguard audit", summary)
            self.assertIn("LF_TAG_VALUES_MISSING", summary)

    def test_cli_plan_github_summary_requires_environment_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stderr = io.StringIO()
            with patch.dict(os.environ, {}, clear=True):
                with contextlib.redirect_stderr(stderr):
                    exit_code = main(
                        [
                            "plan",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--github-summary",
                        ]
                    )

            self.assertEqual(exit_code, 2)
            self.assertIn("GITHUB_STEP_SUMMARY is not set", stderr.getvalue())

    def test_cli_init_writes_valid_starter_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy" / "desired.json"

            exit_code = main(["init", "--output-file", str(output_path)])

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            desired = DesiredState.from_dict(payload)
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(desired.lf_tags), 2)
            self.assertEqual(len(desired.resource_tags), 1)
            self.assertEqual(len(desired.grants), 1)

    def test_cli_init_infers_yaml_format_from_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy" / "desired.yaml"

            exit_code = main(["init", "--output-file", str(output_path)])

            text = output_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertIn("lf_tags:", text)
            self.assertIn("domain:", text)
            self.assertIn("- analytics", text)
            self.assertIn("resource_tags:", text)
            self.assertFalse(text.lstrip().startswith("{"))

    def test_cli_init_json_format_overrides_yaml_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "desired.yaml"

            exit_code = main(["init", "--output-file", str(output_path), "--format", "json"])

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertIn("lf_tags", payload)

    def test_cli_init_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "desired.json"
            output_path.write_text("{}", encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["init", "--output-file", str(output_path)])

            self.assertEqual(exit_code, 2)
            self.assertIn("already exists", stderr.getvalue())
            self.assertEqual(output_path.read_text(encoding="utf-8"), "{}")

    def test_cli_sample_writes_runnable_offline_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["sample", "--output-dir", str(output_dir)])

            desired_path = output_dir / "desired.json"
            current_path = output_dir / "current-snapshot.json"
            readme_path = output_dir / "README.md"
            desired = DesiredState.from_dict(json.loads(desired_path.read_text(encoding="utf-8")))
            current = CurrentState.from_dict(json.loads(current_path.read_text(encoding="utf-8")))
            sample_readme = readme_path.read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn("lfguard plan --desired", stdout.getvalue())
            self.assertIn("README.md", stdout.getvalue())
            self.assertEqual(len(desired.lf_tags), 2)
            self.assertEqual(len(current.lf_tags), 2)
            self.assertIn("lfguard Demo", sample_readme)
            self.assertIn("lfguard audit --desired desired.json", sample_readme)
            self.assertIn("lfguard plan --desired desired.json", sample_readme)

            plan_stdout = io.StringIO()
            with contextlib.redirect_stdout(plan_stdout):
                plan_exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                    ]
                )

            self.assertEqual(plan_exit_code, 0)
            self.assertIn("Plan: 3 change(s), 3 safe, 0 destructive.", plan_stdout.getvalue())

    def test_cli_sample_can_write_yaml_demo_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["sample", "--output-dir", str(output_dir), "--format", "yaml"])

            desired_path = output_dir / "desired.yaml"
            current_path = output_dir / "current-snapshot.yaml"
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertTrue(desired_path.exists())
            self.assertTrue(current_path.exists())
            self.assertFalse((output_dir / "desired.json").exists())
            self.assertIn("lfguard[yaml]", readme)
            self.assertIn("desired.yaml", readme)
            self.assertIn("current-snapshot.yaml", readme)
            self.assertIn("desired.yaml", stdout.getvalue())

    def test_cli_sample_can_write_both_json_and_yaml_demo_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["sample", "--output-dir", str(output_dir), "--format", "both"])
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            for name in ("desired.json", "current-snapshot.json", "desired.yaml", "current-snapshot.yaml"):
                self.assertTrue((output_dir / name).exists(), name)
            self.assertIn("both JSON and YAML state files", readme)
            self.assertIn("YAML state files require", readme)

    def test_cli_sample_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"
            output_dir.mkdir()
            desired_path = output_dir / "desired.json"
            desired_path.write_text("{}", encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["sample", "--output-dir", str(output_dir)])

            self.assertEqual(exit_code, 2)
            self.assertIn("already exists", stderr.getvalue())
            self.assertEqual(desired_path.read_text(encoding="utf-8"), "{}")

    def test_cli_schema_outputs_json_schema(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["schema"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(payload["title"], "lfguard state")
        self.assertIn("lfTagPolicyResource", payload["$defs"])

    def test_cli_doctor_outputs_json_report(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["doctor", "--output", "json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertIn("version", payload)
        self.assertIn("python", payload)
        self.assertEqual(payload["optional_dependencies"]["boto3"]["extra"], "aws")
        self.assertEqual(payload["optional_dependencies"]["PyYAML"]["extra"], "yaml")
        self.assertFalse(payload["aws_calls_made"])

    def test_cli_doctor_outputs_text_report(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["doctor"])

        self.assertEqual(exit_code, 0)
        self.assertIn("lfguard:", stdout.getvalue())
        self.assertIn("Optional dependencies:", stdout.getvalue())
        self.assertIn("No AWS calls were made.", stdout.getvalue())

    def test_cli_doctor_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "artifacts" / "doctor.json"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["doctor", "--output", "json", "--output-file", str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("version", payload)
            self.assertIn("optional_dependencies", payload)
            self.assertFalse(payload["aws_calls_made"])

    def test_cli_doctor_can_fail_when_required_extra_is_missing(self):
        stdout = io.StringIO()
        with patch("lakeformation_guard.cli.util.find_spec", return_value=None):
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["doctor", "--require", "yaml", "--output", "json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["required_extras"], ["yaml"])
        self.assertEqual(payload["missing_required_extras"], ["yaml"])
        self.assertFalse(payload["optional_dependencies"]["PyYAML"]["installed"])

    def test_cli_validate_outputs_json_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "resource_tags": [
                            {
                                "resource": {"kind": "database", "database": "analytics"},
                                "tags": {"sensitivity": ["internal"]},
                            }
                        ],
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "database", "database": "analytics"},
                                "permissions": ["DESCRIBE"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "validate",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                payload,
                {
                    "current_snapshot": {"grants": 0, "lf_tags": 0, "resource_tags": 0, "valid": True},
                    "desired": {"grants": 1, "lf_tags": 1, "resource_tags": 1, "valid": True},
                },
            )

    def test_cli_validate_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "validate.txt"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "resource_tags": [], "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "validate",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output-file",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("Desired state is valid", report)
            self.assertIn("Current snapshot is valid", report)

    def test_cli_version_outputs_short_command_name(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout):
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), "lfguard {}".format(__version__))

    def test_cli_snapshot_outputs_live_current_state_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            output_path = tmp_path / "snapshots" / "prod-current.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "database", "database": "analytics"},
                                "permissions": ["DESCRIBE"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            current = CurrentState.from_dict(
                {
                    "lf_tags": {"sensitivity": ["internal"]},
                    "grants": [
                        {
                            "principal": "role",
                            "resource": {"kind": "database", "database": "analytics"},
                            "permissions": ["DESCRIBE"],
                        }
                    ],
                }
            )

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                adapter_class.from_boto3.return_value.load_current_state_for.return_value = current
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "snapshot",
                            "--desired",
                            str(desired_path),
                            "--profile",
                            "prod",
                            "--output-file",
                            str(output_path),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            adapter_class.from_boto3.assert_called_once_with(
                profile_name="prod",
                region_name=None,
                catalog_id=None,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["lf_tags"], {"sensitivity": ["internal"]})
            self.assertEqual(payload["grants"][0]["resource"]["database"], "analytics")

    def test_cli_apply_dry_run_writes_report_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "lfguard-apply.md"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "apply",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "markdown",
                        "--output-file",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("Dry run: no changes applied.", report)
            self.assertIn("### lfguard plan", report)
            self.assertIn("| safe | lf_tag.create | lf_tag:sensitivity | LF-Tag is missing |", report)

    def test_cli_apply_execute_writes_json_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "lfguard-apply.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")
            apply_result = ApplyResult(
                action="lf_tag.create",
                target="lf_tag:sensitivity",
                applied=True,
                response={"ok": True},
            )

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                adapter_class.from_boto3.return_value.apply.return_value = [apply_result]
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "apply",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--execute",
                            "--output",
                            "json",
                            "--output-file",
                            str(output_path),
                            "--profile",
                            "prod",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            adapter_class.from_boto3.assert_called_once_with(
                profile_name="prod",
                region_name=None,
                catalog_id=None,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["plan"]["summary"], {"total": 1, "safe": 1, "destructive": 0})
            self.assertEqual(payload["results"], [apply_result.to_dict()])


if __name__ == "__main__":
    unittest.main()
