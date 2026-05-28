import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lakeformation_guard import CurrentState, DesiredState, audit
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

    def test_cli_schema_outputs_json_schema(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["schema"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(payload["title"], "lfguard state")
        self.assertIn("lfTagPolicyResource", payload["$defs"])

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

    def test_cli_version_outputs_short_command_name(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout):
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), "lfguard 0.1.0")

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


if __name__ == "__main__":
    unittest.main()
