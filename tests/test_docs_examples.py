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
