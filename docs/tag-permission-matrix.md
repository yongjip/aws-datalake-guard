# LF-Tag and Permission Matrix

This guide maps the practical combinations of AWS Lake Formation LF-Tags and
permissions. Use it when reviewing a desired-state file or explaining why a
principal can see a table, only some columns, or nothing.

## Reading Rules

- IAM and Lake Formation both matter. IAM must allow the API call, and Lake
  Formation must allow the catalog resource or data access.
- Named resource grants ignore LF-Tags. They apply to the named catalog,
  database, table, column set, or data location.
- LF-Tag policy grants match effective LF-Tags on databases, tables, views, or
  columns.
- LF-Tag keys and values are stored lower-case by AWS. Keep desired state
  lower-case.
- A resource can have at most one value for a given LF-Tag key.
- Multiple values for one key in an LF-Tag expression are OR.
- Multiple keys in one LF-Tag expression are AND.
- `*` in an LF-Tag policy grant means all values for that key.

## Effective Tag Values

For one LF-Tag key, the nearest explicit assignment wins.

| Database tag | Table tag | Column tag | Effective table value | Effective column value |
| --- | --- | --- | --- | --- |
| none | none | none | none | none |
| `k=a` | none | none | `a` | `a` |
| `k=a` | `k=b` | none | `b` | `b` |
| `k=a` | none | `k=c` | `a` | `c` |
| `k=a` | `k=b` | `k=c` | `b` | `c` |
| none | `k=b` | none | `b` | `b` |
| none | `k=b` | `k=c` | `b` | `c` |

If the column uses a different key, it keeps inherited keys and adds the new
key:

| Table tag | Column tag | Effective column tags |
| --- | --- | --- |
| `sensitivity=internal` | `domain=sales` | `sensitivity=internal`, `domain=sales` |

Removing an explicit lower-level assignment restores inheritance from the
parent. For example, if a table has `k=a`, a column override has `k=b`, and the
column assignment is removed, the column goes back to effective `k=a`.

## Expression Matching

| LF-Tag expression | Matches |
| --- | --- |
| `domain=sales` | Resources with effective `domain=sales`. |
| `domain=sales|finance` | Resources with effective `domain=sales` OR `domain=finance`. |
| `domain=sales AND sensitivity=internal` | Resources with both effective tags. |
| `domain=sales|finance AND sensitivity=internal` | Sales or finance resources that are also internal. |
| `domain=*` | Resources with the `domain` key and any value. |

An expression does not match resources where the key is absent. `domain=*`
matches any value for `domain`, but it still requires the resource to have the
`domain` key.

## Table and Column Scenarios

Assume table `orders` has columns `id`, `amount`, and `email`.

| Scenario | Grant | Result |
| --- | --- | --- |
| Table has `sensitivity=internal`; no column overrides. | `SELECT` on LF-Tag policy `sensitivity=internal` | Principal can select all columns. |
| Table has `sensitivity=internal`; column `email` has `sensitivity=restricted`. | `SELECT` on `sensitivity=internal` | Principal can select inherited internal columns, not `email`. |
| Same table and column tags. | `SELECT` on `sensitivity=restricted` | Principal can select `email` only. |
| Same table and column tags. | `ALTER`, `DROP`, `INSERT`, or `DELETE` through only the restricted column match | Do not rely on this. These are table-level permissions and conflict with partial-column `SELECT` semantics. |
| Table has `domain=sales`; column `email` has `sensitivity=restricted`. | `SELECT` on `domain=sales AND sensitivity=restricted` | Matches `email` only if the column also effectively has `domain=sales` through inheritance. |
| Table has `domain=sales`; column `email` has `domain=privacy`. | `SELECT` on `domain=sales` | Does not match `email`; the column override changes the effective value for that key. |

Column-level access is primarily a `SELECT` concern. AWS allows `SELECT` with
column filtering, but a principal with partial-column `SELECT` cannot also be
granted `ALTER`, `DROP`, `DELETE`, or `INSERT` on the same table. The reverse is
also true: table-level `ALTER`, `DROP`, `DELETE`, or `INSERT` conflicts with
column-filtered `SELECT`.

## Permission Matrix

This matrix describes AWS Lake Formation permission shapes and how `lfguard`
models them.

| Resource shape | AWS permissions | `lfguard` support |
| --- | --- | --- |
| Catalog / Data Catalog | `CREATE_DATABASE`; catalog also has `ALL`, `ALTER`, `DESCRIBE`, `DROP` in the AWS reference. | `catalog` grants are supported. |
| Database | `ALL`, `ALTER`, `CREATE_TABLE`, `DESCRIBE`, `DROP`. | `database` grants and `lf_tag_policy` with `resource_type=DATABASE` are supported. |
| Table | `ALL`, `ALTER`, `DELETE`, `DESCRIBE`, `DROP`, `INSERT`, `SELECT`. | `table` grants and `lf_tag_policy` with `resource_type=TABLE` are supported. |
| Table columns | `SELECT` with included or excluded columns. | `table_with_columns` grants with included columns are supported. |
| Data location | `DATA_LOCATION_ACCESS`. | `data_location` grants are supported. |
| LF-Tag policy - database | Database permissions on databases matching an LF-Tag expression. | Supported as `lf_tag_policy` with `resource_type=DATABASE`. |
| LF-Tag policy - table | Table permissions on tables/views/columns matching an LF-Tag expression. | Supported as `lf_tag_policy` with `resource_type=TABLE`. |
| LF-Tag values | `ASSOCIATE`, `DESCRIBE`, and grant-with-LF-Tag-expression permissions. | Not modeled as desired grants in 0.1.0. Use native Lake Formation administration for LF-Tag permission delegation. |
| LF-Tags themselves | `ALTER`, `DROP`. | `lfguard` can create/update LF-Tag definitions during apply, but does not model administrative LF-Tag delegation grants. |
| Data filters / cell filters | `SELECT`, `DESCRIBE`, `DROP` on filtered table resources. | Not modeled in 0.1.0. Keep row and cell filters in native Lake Formation or infrastructure tooling. |
| Resource links | `DESCRIBE`, `DROP`. | Not modeled separately in 0.1.0. |

## Grant Option

`grantable_permissions` means the principal can delegate those Lake Formation
permissions to another principal. Keep it rare. In `lfguard`, declare it only
when delegation is the intent:

```json
{
  "principal": "arn:aws:iam::111122223333:role/DataSteward",
  "resource": {
    "kind": "lf_tag_policy",
    "resource_type": "TABLE",
    "expression": {"domain": ["sales"]}
  },
  "permissions": ["SELECT", "DESCRIBE"],
  "grantable_permissions": ["SELECT"]
}
```

Do not use grant option with column-filtered `SELECT`; AWS does not allow grant
option when column filtering is applied.

## Review Checklist

- Does every LF-Tag key/value in assignments and expressions exist in
  `lf_tags`?
- Are tag keys and values lower-case?
- Does each resource assign at most one value per key?
- Are column overrides intentional, especially for sensitive columns?
- Does every LF-Tag expression use OR within values and AND across keys
  intentionally?
- Is `*` used only when all values for a key are truly intended?
- Are partial-column `SELECT` grants kept separate from table-level mutation
  permissions?
- Are destructive operations and grant-option delegation reviewed separately?

## Source References

- [AWS Lake Formation permissions reference](https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-reference.html)
- [Assigning LF-Tags to Data Catalog resources](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-assigning-tags.html)
- [Creating LF-Tag expressions](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-creating-tag-expressions.html)
- [Granting data lake permissions using LF-TBAC](https://docs.aws.amazon.com/lake-formation/latest/dg/granting-catalog-perms-TBAC.html)
- [Managing LF-Tag value permissions](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-granting-tags.html)
- [Updating LF-Tags](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-updating-tags.html)
- [Deleting LF-Tags](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-deleting-tags.html)
