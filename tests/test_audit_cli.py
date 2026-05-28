import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lakeformation_guard import CurrentState, DesiredState, __version__, audit, lint_desired
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

    def test_cli_audit_outputs_sarif(self):
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
                        "sarif",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            run = payload["runs"][0]
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["version"], "2.1.0")
            self.assertEqual(run["tool"]["driver"]["name"], "lfguard")
            self.assertEqual(
                [result["ruleId"] for result in run["results"]],
                ["LF_TAG_VALUES_MISSING", "LF_TAG_VALUES_UNMANAGED"],
            )
            self.assertEqual([result["level"] for result in run["results"]], ["error", "warning"])
            self.assertEqual(
                run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
                str(desired_path),
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

    def test_cli_init_can_generate_blank_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy" / "desired.json"

            exit_code = main(["init", "--output-file", str(output_path), "--template", "blank"])

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            desired = DesiredState.from_dict(payload)
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(desired.lf_tags), 0)
            self.assertEqual(len(desired.resource_tags), 0)
            self.assertEqual(len(desired.grants), 0)

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

    def test_cli_bootstrap_writes_policy_repo_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["bootstrap", "--output-dir", str(output_dir)])

            desired_path = output_dir / "policy" / "desired.json"
            schema_path = output_dir / "policy" / "lfguard.schema.json"
            workflow_path = output_dir / ".github" / "workflows" / "lfguard-policy.yml"
            pre_commit_path = output_dir / ".pre-commit-config.yaml"
            readme_path = output_dir / "README.md"
            desired = DesiredState.from_dict(json.loads(desired_path.read_text(encoding="utf-8")))
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            workflow = workflow_path.read_text(encoding="utf-8")
            pre_commit = pre_commit_path.read_text(encoding="utf-8")
            readme = readme_path.read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn("lfguard policy bootstrap", stdout.getvalue())
            self.assertEqual(len(desired.lf_tags), 2)
            self.assertEqual(schema["title"], "lfguard state")
            self.assertIn("python -m pip install lfguard", workflow)
            self.assertIn("lfguard validate", workflow)
            self.assertIn("lfguard lint", workflow)
            self.assertIn("lfguard summary", workflow)
            self.assertIn("actions/upload-artifact@v4", workflow)
            self.assertIn("lfguard validate --desired policy/desired.json", pre_commit)
            self.assertIn("lfguard Policy Bootstrap", readme)

    def test_cli_bootstrap_can_write_yaml_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(["bootstrap", "--output-dir", str(output_dir), "--format", "yaml"])

            workflow = (output_dir / ".github" / "workflows" / "lfguard-policy.yml").read_text(encoding="utf-8")
            pre_commit = (output_dir / ".pre-commit-config.yaml").read_text(encoding="utf-8")
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "policy" / "desired.yaml").exists())
            self.assertFalse((output_dir / "policy" / "desired.json").exists())
            self.assertIn('python -m pip install "lfguard[yaml]"', workflow)
            self.assertIn("lfguard doctor --require yaml", workflow)
            self.assertIn("lfguard validate --desired policy/desired.yaml", pre_commit)
            self.assertIn('python -m pip install "lfguard[yaml]"', readme)

    def test_cli_bootstrap_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["bootstrap", "--output-dir", str(output_dir)]), 0)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["bootstrap", "--output-dir", str(output_dir)])

            self.assertEqual(exit_code, 2)
            self.assertIn("already exists", stderr.getvalue())

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
            self.assertIn("lfguard lint --desired desired.json", sample_readme)
            self.assertIn("lfguard summary --desired desired.json", sample_readme)
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

    def test_cli_sample_can_include_github_actions_demo_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["sample", "--output-dir", str(output_dir), "--include-ci"])

            workflow_path = output_dir / ".github" / "workflows" / "lfguard-demo.yml"
            workflow = workflow_path.read_text(encoding="utf-8")
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn(str(workflow_path), stdout.getvalue())
            self.assertIn("GitHub Actions Demo", readme)
            self.assertIn("python -m pip install lfguard", workflow)
            self.assertIn("lfguard validate --desired lfguard-demo/desired.json", workflow)
            self.assertIn("lfguard lint --desired lfguard-demo/desired.json --fail-on-findings", workflow)
            self.assertIn("actions/upload-artifact@v4", workflow)

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

    def test_cli_sample_ci_workflow_installs_yaml_extra_for_yaml_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(["sample", "--output-dir", str(output_dir), "--format", "yaml", "--include-ci"])

            workflow = (output_dir / ".github" / "workflows" / "lfguard-demo.yml").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn('python -m pip install "lfguard[yaml]"', workflow)
            self.assertIn("lfguard validate --desired lfguard-demo/desired.yaml", workflow)
            self.assertIn("--current-snapshot lfguard-demo/current-snapshot.yaml", workflow)

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

    def test_cli_permissions_outputs_read_only_policy_by_default(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["permissions"])

        payload = json.loads(stdout.getvalue())
        actions = _policy_actions(payload)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["Version"], "2012-10-17")
        self.assertIn("lakeformation:GetLFTag", actions)
        self.assertIn("lakeformation:GetResourceLFTags", actions)
        self.assertIn("lakeformation:ListPermissions", actions)
        self.assertNotIn("lakeformation:GrantPermissions", actions)

    def test_cli_permissions_can_include_glue_read_and_write_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "artifacts" / "permissions.md"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "permissions",
                        "--template",
                        "additive-apply",
                        "--include-glue-read",
                        "--output",
                        "markdown",
                        "--output-file",
                        str(output_path),
                    ]
                )

            text = output_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("### lfguard permissions: additive-apply", text)
            self.assertIn("lakeformation:GrantPermissions", text)
            self.assertIn("glue:GetTable", text)
            self.assertNotIn("lakeformation:RevokePermissions", text)

    def test_cli_permissions_destructive_apply_policy_includes_revoke_actions(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["permissions", "--template", "destructive-apply", "--output", "json"])

        actions = _policy_actions(json.loads(stdout.getvalue()))
        self.assertEqual(exit_code, 0)
        self.assertIn("lakeformation:RemoveLFTagsFromResource", actions)
        self.assertIn("lakeformation:RevokePermissions", actions)

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

    def test_lint_desired_api_reports_undefined_tag_references(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"domain": ["sales"], "sensitivity": ["restricted"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"], "sensitivity": ["external"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual(
            [finding.code for finding in findings],
            [
                "RESOURCE_TAG_KEY_UNDEFINED",
                "RESOURCE_TAG_VALUE_UNDEFINED",
                "LF_TAG_POLICY_KEY_UNDEFINED",
                "LF_TAG_POLICY_VALUE_UNDEFINED",
            ],
        )

    def test_cli_lint_outputs_json_and_can_fail_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "resource_tags": [
                            {
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "tags": {"sensitivity": ["restricted"]},
                            }
                        ],
                        "grants": [],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "lint",
                        "--desired",
                        str(desired_path),
                        "--output",
                        "json",
                        "--fail-on-findings",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["summary"], {"total": 1, "errors": 1, "warnings": 0})
            self.assertEqual(payload["findings"][0]["code"], "RESOURCE_TAG_VALUE_UNDEFINED")

    def test_cli_lint_outputs_sarif(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "resource_tags": [
                            {
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "tags": {"sensitivity": ["restricted"]},
                            }
                        ],
                        "grants": [],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["lint", "--desired", str(desired_path), "--output", "sarif"])

            payload = json.loads(stdout.getvalue())
            result = payload["runs"][0]["results"][0]
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["version"], "2.1.0")
            self.assertEqual(payload["runs"][0]["tool"]["driver"]["name"], "lfguard")
            self.assertEqual(result["ruleId"], "RESOURCE_TAG_VALUE_UNDEFINED")
            self.assertEqual(result["level"], "error")
            self.assertEqual(
                result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
                str(desired_path),
            )

    def test_cli_lint_warning_only_can_pass_when_failing_on_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            desired_path = Path(tmp) / "desired.json"
            desired_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "lint",
                        "--desired",
                        str(desired_path),
                        "--output",
                        "markdown",
                        "--fail-on-findings",
                        "--fail-on-severity",
                        "error",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard lint", stdout.getvalue())
            self.assertIn("DESIRED_STATE_EMPTY", stdout.getvalue())

    def test_cli_lint_writes_github_summary_before_failing_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            summary_path = tmp_path / "summary.md"
            desired_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "lint",
                            "--desired",
                            str(desired_path),
                            "--fail-on-findings",
                            "--github-summary",
                        ]
                    )

            self.assertEqual(exit_code, 1)
            self.assertIn("Lint findings:", stdout.getvalue())
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("### lfguard lint", summary)
            self.assertIn("DESIRED_STATE_EMPTY", summary)

    def test_cli_summary_outputs_policy_inventory_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"], "domain": ["sales"]},
                        "resource_tags": [
                            {
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "tags": {"sensitivity": ["internal"], "domain": ["sales"]},
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
            current_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "summary",
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
            self.assertEqual(payload["desired"]["lf_tag_keys"], ["domain", "sensitivity"])
            self.assertEqual(payload["desired"]["resource_kinds"], {"table": 1})
            self.assertEqual(payload["desired"]["grant_principals"], ["role"])
            self.assertEqual(payload["desired"]["grant_resource_kinds"], {"database": 1})
            self.assertEqual(payload["desired"]["permissions"], ["DESCRIBE"])
            self.assertEqual(payload["current_snapshot"]["lf_tags"], 1)

    def test_cli_summary_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            desired_path = Path(tmp) / "desired.json"
            desired_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["summary", "--desired", str(desired_path), "--output", "markdown"])

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard summary", stdout.getvalue())
            self.assertIn("| LF-Tag definitions | 1 (sensitivity) |", stdout.getvalue())

    def test_cli_summary_writes_github_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            summary_path = tmp_path / "summary.md"
            desired_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["summary", "--desired", str(desired_path), "--github-summary"])

            self.assertEqual(exit_code, 0)
            self.assertIn("Desired summary:", stdout.getvalue())
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("### lfguard summary", summary)
            self.assertIn("| LF-Tag definitions | 1 (sensitivity) |", summary)

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


def _policy_actions(policy):
    return {
        action
        for statement in policy["Statement"]
        for action in statement["Action"]
    }


if __name__ == "__main__":
    unittest.main()
