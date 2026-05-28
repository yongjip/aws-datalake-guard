"""JSON Schema helpers for guardrail state files."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


_STRING_VALUE = {"type": "string", "minLength": 1}
_VALUE_LIST = {
    "oneOf": [
        _STRING_VALUE,
        {
            "type": "array",
            "items": _STRING_VALUE,
            "minItems": 1,
            "uniqueItems": True,
        },
    ]
}

STATE_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://raw.githubusercontent.com/yongjip/aws-datalake-guard/main/docs/schema.json",
    "title": "lfguard state",
    "description": "Desired or current AWS Lake Formation LF-Tag guardrail state.",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "lf_tags": {
            "description": "LF-Tag keys and allowed values.",
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": _VALUE_LIST,
                },
                {
                    "type": "array",
                    "items": {"$ref": "#/$defs/lfTagDefinition"},
                },
            ],
        },
        "resource_tags": {
            "type": "array",
            "items": {"$ref": "#/$defs/resourceTagAssignment"},
        },
        "grants": {
            "type": "array",
            "items": {"$ref": "#/$defs/grant"},
        },
    },
    "$defs": {
        "lfTagDefinition": {
            "type": "object",
            "additionalProperties": False,
            "required": ["key", "values"],
            "properties": {
                "key": _STRING_VALUE,
                "values": _VALUE_LIST,
            },
        },
        "resourceTagAssignment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["resource", "tags"],
            "properties": {
                "resource": {"$ref": "#/$defs/resource"},
                "tags": {
                    "type": "object",
                    "additionalProperties": _VALUE_LIST,
                },
            },
        },
        "grant": {
            "type": "object",
            "additionalProperties": False,
            "required": ["principal", "resource", "permissions"],
            "properties": {
                "principal": _STRING_VALUE,
                "resource": {"$ref": "#/$defs/resource"},
                "permissions": _VALUE_LIST,
                "grantable_permissions": _VALUE_LIST,
            },
        },
        "resource": {
            "oneOf": [
                {"$ref": "#/$defs/catalogResource"},
                {"$ref": "#/$defs/databaseResource"},
                {"$ref": "#/$defs/tableResource"},
                {"$ref": "#/$defs/tableWithColumnsResource"},
                {"$ref": "#/$defs/dataLocationResource"},
                {"$ref": "#/$defs/lfTagPolicyResource"},
            ],
        },
        "catalogResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {
                "kind": {"const": "catalog"},
                "catalog_id": _STRING_VALUE,
            },
        },
        "databaseResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "database"],
            "properties": {
                "kind": {"const": "database"},
                "catalog_id": _STRING_VALUE,
                "database": _STRING_VALUE,
            },
        },
        "tableResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "database", "table"],
            "properties": {
                "kind": {"const": "table"},
                "catalog_id": _STRING_VALUE,
                "database": _STRING_VALUE,
                "table": _STRING_VALUE,
            },
        },
        "tableWithColumnsResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "database", "table", "columns"],
            "properties": {
                "kind": {"const": "table_with_columns"},
                "catalog_id": _STRING_VALUE,
                "database": _STRING_VALUE,
                "table": _STRING_VALUE,
                "columns": {
                    "type": "array",
                    "items": _STRING_VALUE,
                    "minItems": 1,
                    "uniqueItems": True,
                },
            },
        },
        "dataLocationResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "location"],
            "properties": {
                "kind": {"const": "data_location"},
                "catalog_id": _STRING_VALUE,
                "location": _STRING_VALUE,
            },
        },
        "lfTagPolicyResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "resource_type", "expression"],
            "properties": {
                "kind": {"const": "lf_tag_policy"},
                "resource_type": {"enum": ["DATABASE", "TABLE"]},
                "expression": {
                    "oneOf": [
                        {
                            "type": "object",
                            "additionalProperties": _VALUE_LIST,
                        },
                        {
                            "type": "array",
                            "items": {"$ref": "#/$defs/lfTagDefinition"},
                            "minItems": 1,
                        },
                    ],
                },
            },
        },
    },
}


def state_json_schema() -> Dict[str, Any]:
    """Return a JSON Schema for desired/current state files."""

    return deepcopy(STATE_JSON_SCHEMA)
