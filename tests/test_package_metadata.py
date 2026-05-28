import configparser
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

    def test_changelog_and_publishing_docs_reference_current_version(self):
        changelog = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        publishing = (self.root / "docs" / "publishing.md").read_text(encoding="utf-8")

        self.assertIn("## {}".format(__version__), changelog)
        self.assertIn("v{}".format(__version__), publishing)

    def test_console_scripts_include_primary_command_and_alias(self):
        console_scripts = self.config["options.entry_points"]["console_scripts"]

        self.assertIn("lfguard = lakeformation_guard.cli:main", console_scripts)
        self.assertIn("aws-lakeformation-guard = lakeformation_guard.cli:main", console_scripts)

    def test_project_urls_cover_user_evaluation_docs(self):
        project_urls = self.config["metadata"]["project_urls"]

        for label in (
            "Documentation",
            "CLI Reference",
            "Report Formats",
            "Safety Model",
            "State Format",
            "AWS API Coverage",
            "Examples",
            "Changelog",
            "Security",
        ):
            self.assertIn("{} =".format(label), project_urls)
