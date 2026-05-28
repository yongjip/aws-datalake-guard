import json
import re
import unittest
from pathlib import Path

from lakeformation_guard import DesiredState, Grant, ResourceRef


class DocumentationExampleTests(unittest.TestCase):
    def test_internal_markdown_links_resolve(self):
        root = Path(__file__).resolve().parents[1]
        docs_paths = [
            root / "README.md",
            *sorted((root / ".github").glob("*.md")),
            *sorted((root / ".github" / "ISSUE_TEMPLATE").glob("*.md")),
            *sorted((root / "docs").rglob("*.md")),
            *sorted((root / "examples").glob("*.md")),
            root / "CHANGELOG.md",
            root / "CONTRIBUTING.md",
            root / "SECURITY.md",
        ]
        link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")

        for docs_path in docs_paths:
            text = docs_path.read_text(encoding="utf-8")
            for match in link_pattern.finditer(text):
                target = match.group(1).strip()
                if not target or _is_external_link(target) or target.startswith("#"):
                    continue
                target_path = target.split("#", 1)[0]
                if not target_path:
                    continue
                resolved = (docs_path.parent / target_path).resolve()
                self.assertTrue(
                    resolved.exists(),
                    "{} links to missing {}".format(docs_path.relative_to(root), target),
                )

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

    def test_code_scanning_workflow_uploads_lint_and_audit_sarif(self):
        root = Path(__file__).resolve().parents[1]
        workflow_text = (root / "examples" / "github-actions" / "lakeformation-code-scanning.yml").read_text(
            encoding="utf-8"
        )

        for expected in (
            "security-events: write",
            "github/codeql-action/upload-sarif@v3",
            "artifacts/lfguard-lint.sarif",
            "artifacts/lfguard-audit.sarif",
            "artifacts/lfguard-check.md",
            "lfguard check",
            "category: lfguard-lint",
            "category: lfguard-audit",
        ):
            self.assertIn(expected, workflow_text)

    def test_lake_formation_guide_covers_operating_model(self):
        root = Path(__file__).resolve().parents[1]
        guide_text = (root / "docs" / "lake-formation-guide.md").read_text(encoding="utf-8")
        readme_text = (root / "README.md").read_text(encoding="utf-8")

        for expected in (
            "IAMAllowedPrincipals",
            "hybrid access mode",
            "Best Practices",
            "Antipatterns",
            "AWS stores LF-Tag keys and values in lower case",
            "only one value for a given key",
            "are OR. Multiple keys are AND",
            "`*` as all values for a tag key",
            "Source References",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-overview.html",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/tag-based-access-control.html",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/lf-tag-considerations.html",
        ):
            self.assertIn(expected, guide_text)
        self.assertIn("docs/lake-formation-guide.md", readme_text)

    def test_tag_permission_matrix_covers_effective_tag_and_permission_cases(self):
        root = Path(__file__).resolve().parents[1]
        matrix_text = (root / "docs" / "tag-permission-matrix.md").read_text(encoding="utf-8")
        readme_text = (root / "README.md").read_text(encoding="utf-8")

        for expected in (
            "Effective Tag Values",
            "Expression Matching",
            "Table and Column Scenarios",
            "Permission Matrix",
            "Grant Option",
            "`k=a` | `k=b` | `k=c`",
            "`domain=sales|finance AND sensitivity=internal`",
            "Table has `sensitivity=internal`; column `email` has `sensitivity=restricted`.",
            "LF-Tag values",
            "Data filters / cell filters",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-reference.html",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-assigning-tags.html",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-granting-tags.html",
        ):
            self.assertIn(expected, matrix_text)
        self.assertIn("docs/tag-permission-matrix.md", readme_text)


def _is_external_link(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:"))
