import unittest

from lakeformation_guard import Change, CurrentState, DesiredState, Plan, plan
from lakeformation_guard.aws import AWSLakeFormationAdapter, to_lf_resource
from lakeformation_guard.models import ResourceRef


class FakeLakeFormation:
    def __init__(self):
        self.calls = []

    def create_lf_tag(self, **kwargs):
        self.calls.append(("create_lf_tag", kwargs))
        return {"ok": True}

    def add_lf_tags_to_resource(self, **kwargs):
        self.calls.append(("add_lf_tags_to_resource", kwargs))
        return {"ok": True}

    def grant_permissions(self, **kwargs):
        self.calls.append(("grant_permissions", kwargs))
        return {"ok": True}

    def update_lf_tag(self, **kwargs):
        self.calls.append(("update_lf_tag", kwargs))
        return {"ok": True}


class AwsAdapterTests(unittest.TestCase):
    def test_dry_run_does_not_call_lakeformation(self):
        desired = _desired_state()
        change_plan = plan(desired, CurrentState.empty())
        client = FakeLakeFormation()
        adapter = AWSLakeFormationAdapter(client)

        results = adapter.apply(change_plan, dry_run=True)

        self.assertEqual(client.calls, [])
        self.assertEqual(len(results), 3)
        self.assertTrue(all(not result.applied for result in results))

    def test_apply_executes_safe_changes(self):
        desired = _desired_state()
        change_plan = plan(desired, CurrentState.empty())
        client = FakeLakeFormation()
        adapter = AWSLakeFormationAdapter(client, catalog_id="111122223333")

        results = adapter.apply(change_plan, dry_run=False)

        self.assertEqual([name for name, _ in client.calls], ["create_lf_tag", "add_lf_tags_to_resource", "grant_permissions"])
        self.assertEqual(client.calls[0][1]["CatalogId"], "111122223333")
        self.assertEqual(client.calls[2][1]["Permissions"], ["SELECT"])
        self.assertTrue(all(result.applied for result in results))

    def test_destructive_changes_are_skipped_without_allowance(self):
        change_plan = Plan(
            (
                Change(
                    action="lf_tag.remove_values",
                    target="lf_tag:sensitivity",
                    reason="extra value",
                    payload={"tag_key": "sensitivity", "tag_values": ["restricted"]},
                    destructive=True,
                ),
            )
        )
        client = FakeLakeFormation()
        adapter = AWSLakeFormationAdapter(client)

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=False)

        self.assertEqual(results, [])
        self.assertEqual(client.calls, [])

    def test_lf_tag_policy_resource_conversion(self):
        resource = ResourceRef.from_dict(
            {
                "kind": "lf_tag_policy",
                "resource_type": "TABLE",
                "expression": {"domain": ["sales"], "sensitivity": ["internal"]},
            }
        )

        self.assertEqual(
            to_lf_resource(resource),
            {
                "LFTagPolicy": {
                    "ResourceType": "TABLE",
                    "Expression": [
                        {"TagKey": "domain", "TagValues": ["sales"]},
                        {"TagKey": "sensitivity", "TagValues": ["internal"]},
                    ],
                }
            },
        )


def _desired_state():
    return DesiredState.from_dict(
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


if __name__ == "__main__":
    unittest.main()
