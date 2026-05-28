import configparser
import re
import unittest
from pathlib import Path

from lakeformation_guard import __version__


class PackageMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.config = configparser.ConfigParser()
        cls.config.read(cls.root / "setup.cfg", encoding="utf-8")

    def test_setup_version_matches_imported_version(self):
        self.assertEqual(self.config["metadata"]["version"], __version__)

    def test_build_system_uses_modern_setuptools_backend(self):
        pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('build-backend = "setuptools.build_meta"', pyproject)
        self.assertRegex(pyproject, r'requires = \["setuptools>=70\.1"\]')
        self.assertIsNone(re.search(r'"wheel"', pyproject))

    def test_changelog_and_publishing_docs_reference_current_version(self):
        changelog = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        publishing = (self.root / "docs" / "publishing.md").read_text(encoding="utf-8")

        self.assertIn("## {}".format(__version__), changelog)
        self.assertIn("v{}".format(__version__), publishing)

    def test_console_scripts_include_primary_command_and_alias(self):
        console_scripts = self.config["options.entry_points"]["console_scripts"]

        self.assertIn("lfguard = lakeformation_guard.cli:main", console_scripts)
        self.assertIn("aws-lakeformation-guard = lakeformation_guard.cli:main", console_scripts)

    def test_license_metadata_uses_spdx_expression(self):
        metadata = self.config["metadata"]
        classifiers = metadata["classifiers"]

        self.assertEqual(metadata["license"], "Apache-2.0")
        self.assertIn("license_files = LICENSE", (self.root / "setup.cfg").read_text(encoding="utf-8"))
        self.assertNotIn("License ::", classifiers)

    def test_source_distribution_includes_example_workflows(self):
        manifest = (self.root / "MANIFEST.in").read_text(encoding="utf-8")

        self.assertIn("recursive-include examples *.json *.md *.yaml *.yml", manifest)
        self.assertTrue((self.root / "examples" / "github-actions" / "lakeformation-drift.yml").exists())
        self.assertTrue((self.root / "examples" / "pre-commit" / "pre-commit-config.yaml").exists())

    def test_project_urls_cover_user_evaluation_docs(self):
        project_urls = self.config["metadata"]["project_urls"]

        for label in (
            "Documentation",
            "CLI Reference",
            "Adoption Checklist",
            "Report Formats",
            "Architecture",
            "Roadmap",
            "Safety Model",
            "Lake Formation Guide",
            "Tag and Permission Matrix",
            "Positioning",
            "State Format",
            "AWS API Coverage",
            "FAQ",
            "Troubleshooting",
            "Examples",
            "Changelog",
            "Security",
        ):
            self.assertIn("{} =".format(label), project_urls)

    def test_keywords_cover_discovery_terms(self):
        keywords = self.config["metadata"]["keywords"]

        for keyword in (
            "policy-as-code",
            "drift-detection",
            "data-governance",
            "data-lake",
            "aws-glue",
            "permissions",
        ):
            self.assertIn(keyword, keywords)

    def test_ci_and_release_smoke_cover_primary_cli_paths(self):
        workflow_paths = (
            self.root / ".github" / "workflows" / "ci.yml",
            self.root / ".github" / "workflows" / "release.yml",
        )

        for workflow_path in workflow_paths:
            workflow = workflow_path.read_text(encoding="utf-8")
            self.assertIn("/lfguard --version", workflow)
            self.assertIn("/aws-lakeformation-guard --version", workflow)
            self.assertIn("/lfguard check", workflow)
            self.assertIn("--current-snapshot /tmp/lfguard-demo/current-snapshot.json", workflow)

    def test_release_workflow_verifies_published_package(self):
        workflow = (self.root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertIn("Validate release tag", workflow)
        self.assertIn("package_version=", workflow)
        self.assertIn("release_version=", workflow)
        self.assertIn("Verify distribution versions", workflow)
        self.assertIn("dist/lfguard-${version}.tar.gz", workflow)
        self.assertIn("lfguard-{}.dist-info/METADATA", workflow)
        self.assertIn("lfguard-{}/PKG-INFO", workflow)
        self.assertIn("verify-pypi:", workflow)
        self.assertIn("needs: publish", workflow)
        self.assertIn("RELEASE_TAG: ${{ github.event.release.tag_name }}", workflow)
        self.assertIn('python -m pip install --no-cache-dir "lfguard==${version}"', workflow)
        self.assertIn('test "$(lfguard --version)" = "lfguard ${version}"', workflow)
        self.assertIn("sleep 15", workflow)
        self.assertIn("lfguard sample --output-dir /tmp/lfguard-pypi-demo", workflow)
        self.assertIn("aws-lakeformation-guard --version", workflow)
