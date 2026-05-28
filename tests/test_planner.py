import unittest

from lakeformation_guard import CurrentState, DesiredState, PlanOptions, plan


class PlannerTests(unittest.TestCase):
    def test_plan_adds_missing_lf_tags_resource_tags_and_grants(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/Analyst",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        change_plan = plan(desired, CurrentState.empty())

        self.assertEqual(
            [change.action for change in change_plan.changes],
            ["lf_tag.create", "resource_tag.add_values", "grant.add_permissions"],
        )
        self.assertEqual(change_plan.summary(), {"total": 3, "safe": 3, "destructive": 0})

    def test_plan_omits_destructive_changes_by_default(self):
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
                "lf_tags": {"sensitivity": ["internal", "restricted"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE", "DROP"],
                    }
                ],
            }
        )

        change_plan = plan(desired, current)

        self.assertEqual(change_plan.changes, ())

    def test_plan_includes_destructive_changes_when_allowed(self):
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
                "lf_tags": {"sensitivity": ["internal", "restricted"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE", "DROP"],
                    },
                    {
                        "principal": "other-role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    },
                ],
            }
        )

        change_plan = plan(
            desired,
            current,
            PlanOptions(allow_lf_tag_value_removals=True, allow_permission_revokes=True),
        )

        self.assertEqual(
            [change.action for change in change_plan.changes],
            ["lf_tag.remove_values", "grant.revoke_permissions", "grant.revoke_permissions"],
        )
        self.assertTrue(all(change.destructive for change in change_plan.changes))


if __name__ == "__main__":
    unittest.main()
