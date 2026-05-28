import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

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

    def test_cli_version_outputs_short_command_name(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout):
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), "lfguard 0.1.0")


if __name__ == "__main__":
    unittest.main()
