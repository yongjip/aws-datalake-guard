# State File Format

`lfguard` desired-state and current-snapshot files use the same JSON/YAML shape.
Desired files describe what should exist; current snapshots describe what exists
now.

```json
{
  "lf_tags": {},
  "resource_tags": [],
  "grants": []
}
```

All top-level sections are optional, but real policies normally use at least one
of them.

## LF-Tag Definitions

Use `lf_tags` to define LF-Tag keys and allowed values:

```json
{
  "lf_tags": {
    "domain": ["sales", "finance"],
    "sensitivity": ["public", "internal", "restricted"]
  }
}
```

The equivalent list form is also accepted:

```json
{
  "lf_tags": [
    {"key": "domain", "values": ["sales", "finance"]},
    {"key": "sensitivity", "values": ["public", "internal", "restricted"]}
  ]
}
```

Single values may be written as strings anywhere a value list is accepted.

## Resource Tag Assignments

Use `resource_tags` to attach LF-Tags to Data Catalog resources:

```json
{
  "resource_tags": [
    {
      "resource": {
        "kind": "table",
        "database": "analytics",
        "table": "orders"
      },
      "tags": {
        "domain": ["sales"],
        "sensitivity": ["internal"]
      }
    }
  ]
}
```

Supported resource kinds are shown below. `catalog_id` is optional for each
resource kind when you need to target a specific Glue Data Catalog.

### Catalog

```json
{"kind": "catalog"}
```

With an explicit catalog:

```json
{"kind": "catalog", "catalog_id": "111122223333"}
```

### Database

```json
{
  "kind": "database",
  "database": "analytics"
}
```

### Table

```json
{
  "kind": "table",
  "database": "analytics",
  "table": "orders"
}
```

### Table Columns

```json
{
  "kind": "table_with_columns",
  "database": "analytics",
  "table": "orders",
  "columns": ["order_id", "customer_id"]
}
```

### Data Location

```json
{
  "kind": "data_location",
  "location": "arn:aws:s3:::analytics-lake/raw/"
}
```

### LF-Tag Policy

LF-Tag policy resources are used for grants. `resource_type` must be `DATABASE`
or `TABLE`.

```json
{
  "kind": "lf_tag_policy",
  "resource_type": "TABLE",
  "expression": {
    "domain": ["sales"],
    "sensitivity": ["public", "internal"]
  }
}
```

Expression list form is also accepted:

```json
{
  "kind": "lf_tag_policy",
  "resource_type": "TABLE",
  "expression": [
    {"key": "domain", "values": ["sales"]},
    {"key": "sensitivity", "values": ["public", "internal"]}
  ]
}
```

## Grants

Use `grants` to declare Lake Formation permissions for a principal and resource:

```json
{
  "grants": [
    {
      "principal": "arn:aws:iam::111122223333:role/Analyst",
      "resource": {
        "kind": "database",
        "database": "analytics"
      },
      "permissions": ["DESCRIBE"]
    }
  ]
}
```

Grantable permissions are optional. They are automatically included in
`permissions` during normalization:

```json
{
  "principal": "arn:aws:iam::111122223333:role/DataAdmin",
  "resource": {
    "kind": "table",
    "database": "analytics",
    "table": "orders"
  },
  "permissions": ["SELECT", "DESCRIBE"],
  "grantable_permissions": ["SELECT"]
}
```

Use LF-Tag policy grants for attribute-based access:

```json
{
  "principal": "arn:aws:iam::111122223333:role/Analyst",
  "resource": {
    "kind": "lf_tag_policy",
    "resource_type": "TABLE",
    "expression": {
      "domain": ["sales"],
      "sensitivity": ["public", "internal"]
    }
  },
  "permissions": ["SELECT", "DESCRIBE"]
}
```

## Normalization

`lfguard` normalizes state files before auditing or planning:

- resource kinds are lowercased and hyphen-insensitive, so `table-with-columns`
  is read as `table_with_columns`;
- permissions are uppercased;
- repeated values are deduplicated and sorted;
- empty strings are ignored in value lists;
- unsupported resource kinds or missing required fields fail validation with
  exit code `2`.

Run this before CI drift checks:

```bash
lfguard validate --desired policy/desired.json
```

For editor integration, export the JSON Schema:

```bash
lfguard schema --output-file policy/lfguard.schema.json
```
