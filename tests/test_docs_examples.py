import json
import re
import unittest
from pathlib import Path

from lakeformation_guard import DesiredState, Grant, ResourceRef


class DocumentationExampleTests(unittest.TestCase):
    def test_state_format_json_examples_parse(self):
        docs_path = Path(__file__).resolve().parents[1] / "docs" / "state-format.md"
        text = docs_path.read_text(encoding="utf-8")
        blocks = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)

        self.assertGreater(len(blocks), 0)
        for block in blocks:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("kind"):
                ResourceRef.from_dict(data)
            elif isinstance(data, dict) and "principal" in data:
                Grant.from_dict(data)
            else:
                DesiredState.from_dict(data)

    def test_aws_api_coverage_mentions_adapter_methods(self):
        root = Path(__file__).resolve().parents[1]
        docs_text = (root / "docs" / "aws-api-coverage.md").read_text(encoding="utf-8")
        source_text = (root / "src" / "lakeformation_guard" / "aws.py").read_text(encoding="utf-8")
        methods = (
            "get_lf_tag",
            "get_resource_lf_tags",
            "list_permissions",
            "create_lf_tag",
            "update_lf_tag",
            "add_lf_tags_to_resource",
            "remove_lf_tags_from_resource",
            "grant_permissions",
            "revoke_permissions",
        )

        for method in methods:
            self.assertIn(method, source_text)
            self.assertIn(method, docs_text)

        for action in (
            "lakeformation:GetLFTag",
            "lakeformation:GetResourceLFTags",
            "lakeformation:ListPermissions",
            "lakeformation:CreateLFTag",
            "lakeformation:UpdateLFTag",
            "lakeformation:AddLFTagsToResource",
            "lakeformation:RemoveLFTagsFromResource",
            "lakeformation:GrantPermissions",
            "lakeformation:RevokePermissions",
        ):
            self.assertIn(action, docs_text)
