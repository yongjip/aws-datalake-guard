# Policy Authoring Direction

This is the direction for the next `lfguard` layer. The current package already
supports low-level desired state, lint, audit, plan, and conservative apply.
The next layer should make the safe operating model the easiest way to write
policy.

## Decision

Use a Python-native policy builder as the source of truth for opinionated
permission groups. Generate normal `DesiredState` JSON or YAML from it. Keep
the generated file reviewable, but do not make users hand-author a large YAML
permission DSL.

```text
policy.py -> generated desired.yaml -> lfguard check/audit/plan/apply
```

This keeps the existing core stable while adding a safer authoring surface.

## Core Abstractions

| Concept | Meaning |
| --- | --- |
| Tag key | LF-Tag key metadata: values, where it can be assigned, and which access models may use it as a grant filter. |
| Permission group | Business access intent such as reader, writer, steward, or admin. |
| IAM role binding | Assignment from an IAM role to one or more permission groups. Treat IAM roles as the execution/user-group boundary. |
| Generated desired state | The normal `lfguard` desired policy produced by the builder. |
| Exception | Time-bounded escape hatch with reason, owner, and expiry. |

## Access Models

Access models are not just labels. They define allowed permissions and which tag
filters can be used.

| Access model | Default permissions | Grant filter rules |
| --- | --- | --- |
| `Reader` | `SELECT`, `DESCRIBE` | May use table tags and column-narrowing tags such as `contains_pii=false`. |
| `WholeTableReader` | `SELECT`, `DESCRIBE` | Must use only filters that keep whole-table scope. |
| `Writer` | Whole-table `SELECT`/`DESCRIBE` plus `INSERT`, `DELETE` | Must not use column-narrowing tag filters. Compiles into an atomic generated grant pair. |
| `Editor` | `ALTER`, optional write permissions | Must not use column-narrowing tag filters. Requires review because it changes catalog metadata. |
| `Steward` | tag administration/delegation intent | Separate from data read/write. Requires explicit scope and review. |
| `Admin` | exceptional administration | Requires an exception or deliberately explicit construction. |

The hard rule is:

```text
Readers may be column-filtered. Writers and editors must stay whole-table.
```

Writers should always have reader capability. The distinction is about the
generated Lake Formation grants, not the user's effective capability. A writer
access model should compile to an atomic generated grant pair:

```text
role/DataPipeline -> pipeline_write
pipeline_write -> generated whole-table SELECT/DESCRIBE grant
pipeline_write -> generated INSERT/DELETE grant
```

Do not express that as one grant containing `SELECT` plus
`INSERT`/`DELETE`/`ALTER`/`DROP`.

The two generated grants must not become two user-managed policy objects.
Otherwise drift risk gets larger: a team can accidentally keep the write grant
and lose the whole-table read grant, or change one expression without changing
the other. The authoring layer should keep the permission group as the source of
truth and treat the generated grants as a paired invariant during check, audit,
plan, and report rendering.

## Tag Key Semantics

Tag keys need two separate kinds of metadata:

- where the tag can be assigned;
- which access models may use the tag as a grant filter.

For example, `contains_pii` can be assigned to databases, tables, and columns.
That does not mean it is safe in writer grant filters.

```python
from lakeformation_guard.policy import AccessModel, LakePolicy

policy = LakePolicy()

policy.tag_key(
    "domain",
    values=["sales", "finance", "platform"],
    assignable_to=["database", "table"],
    allowed_grant_models=[AccessModel.READER, AccessModel.WHOLE_TABLE_READER, AccessModel.WRITER],
)

policy.tag_key(
    "sensitivity",
    values=["public", "internal", "restricted"],
    assignable_to=["database", "table", "column"],
    allowed_grant_models=[AccessModel.READER, AccessModel.WHOLE_TABLE_READER, AccessModel.WRITER],
)

policy.tag_key(
    "contains_pii",
    values=["true", "false"],
    assignable_to=["database", "table", "column"],
    allowed_grant_models=[AccessModel.READER],
)
```

`contains_pii` is still valid catalog metadata at any supported level. It is
blocked only as a writer/editor grant filter because it can narrow access to a
subset of columns.

## Generic Authoring Example

Use neutral examples in public docs and tests. Avoid company-specific database
names, role names, and data domains.

```python
from lakeformation_guard.policy import LakePolicy, Reader, WholeTableReader, Writer

policy = LakePolicy()

policy.tag_key(
    "domain",
    values=["sales", "finance", "platform"],
    assignable_to=["database", "table"],
    allowed_grant_models=["reader", "whole_table_reader", "writer"],
)
policy.tag_key(
    "sensitivity",
    values=["public", "internal", "restricted"],
    assignable_to=["database", "table", "column"],
    allowed_grant_models=["reader", "whole_table_reader", "writer"],
)
policy.tag_key(
    "contains_pii",
    values=["true", "false"],
    assignable_to=["database", "table", "column"],
    allowed_grant_models=["reader"],
)

policy.permission_group(
    "analyst_read",
    Reader()
    .where(domain="sales")
    .where(sensitivity=["public", "internal"])
    .where(contains_pii="false"),
)

policy.permission_group(
    "pipeline_write",
    Writer()
    .where(domain="sales")
    .where(sensitivity=["public", "internal", "restricted"]),
)

policy.bind_role(
    "arn:aws:iam::111122223333:role/Analyst",
    ["analyst_read"],
)
policy.bind_role(
    "arn:aws:iam::111122223333:role/DataPipeline",
    ["pipeline_write"],
)

policy.write_desired("policy/desired.yaml")
```

The generated file should include a clear header:

```yaml
# Generated by policy.py. Do not edit directly.
```

## Enforcement Modes

The package can support more than one enforcement mode, but the strict mode
should remain the default for new policy.

| Mode | Purpose | Behavior |
| --- | --- | --- |
| `strict` | New controlled-lake policy. | Blocks unsafe patterns and fails CI on warnings when `--fail-on-findings` is used. |
| `migration` | Moving from console/IAM/table grants toward LF-Tag policy. | Allows selected exceptions only with owner, reason, and expiry. Still blocks known AWS-invalid combinations. |
| `audit` | Discovery and reporting. | Reports violations without generating apply-ready policy. No destructive actions. |

Do not weaken the low-level lints to support migration. Migration should add
explicit exceptions, not silently make risky policy valid.

## Non-Negotiable Guardrails

The authoring layer should fail before generating desired state when it sees:

- writer/editor/admin models using tag keys that are not allowed for those
  grant models;
- any generated LF-Tag `TABLE` grant that combines `SELECT` with `ALTER`,
  `DELETE`, `DROP`, or `INSERT`;
- writer access models that fail to generate whole-table `SELECT`/`DESCRIBE`
  capability alongside write capability;
- writer generated grant pairs that drift apart by expression, principal,
  permissions, or source permission group;
- `ALL` or `SUPER` permissions;
- broad principals such as `IAMAllowedPrincipals`;
- admin/editor access without an explicit exception path;
- expired exceptions;
- ambiguous wildcard usage where an explicit value list is expected.

The existing `lint_desired()` layer remains the backstop. The builder should
catch these earlier with clearer errors tied to permission group names.

## Minimal v0.2.0 Scope

The first implementation should stay small:

- `lakeformation_guard.policy` module.
- `LakePolicy`, `TagKey`, `PermissionGroup`, `RoleBinding`.
- Access model objects: `Reader`, `WholeTableReader`, `Writer`, `Editor`,
  `Admin`.
- `LakePolicy.to_desired_state()`.
- `LakePolicy.write_desired()`.
- Validation that writer/editor groups cannot use reader-only tag filters.
- Validation that generated grants still satisfy `lint_desired()`.
- Documentation and tests with generic examples.

Defer UI, SQL analysis, full access explanation, and account-wide discovery.
Those are useful later, but they are not needed to make the authoring direction
safe and concrete.
