import unittest

from lakeformation_guard.models import DesiredState, ResourceRef


class ModelTests(unittest.TestCase):
    def test_state_from_dict_normalizes_tags_and_grants(self):
        state = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal", "public", "public"]},
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/Analyst",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["describe"],
                    }
                ],
            }
        )

        self.assertEqual(state.lf_tags[0].values, ("internal", "public"))
        self.assertEqual(state.resource_tags[0].resource.identity, "table:database=analytics:table=orders")
        self.assertEqual(state.grants[0].permissions, ("DESCRIBE",))

    def test_lf_tag_policy_resource_identity_is_stable(self):
        first = ResourceRef.from_dict(
            {
                "kind": "lf_tag_policy",
                "resource_type": "table",
                "expression": {"domain": ["sales"], "sensitivity": ["internal", "public"]},
            }
        )
        second = ResourceRef.from_dict(
            {
                "kind": "lf-tag-policy",
                "resource_type": "TABLE",
                "expression": [
                    {"key": "sensitivity", "values": ["public", "internal"]},
                    {"key": "domain", "values": ["sales"]},
                ],
            }
        )

        self.assertEqual(first, second)
        self.assertEqual(
            first.identity,
            "lf_tag_policy:resource_type=TABLE:expression=domain=sales,sensitivity=internal|public",
        )


if __name__ == "__main__":
    unittest.main()
