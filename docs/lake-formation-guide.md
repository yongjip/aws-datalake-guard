# Lake Formation Guide

This is the short operating guide behind `lfguard`. It explains the Lake
Formation model the package assumes, the practices worth automating, and the
traps to avoid.

## The Model

Lake Formation is a permission layer on top of the AWS Glue Data Catalog and
registered data locations. Access succeeds only when both layers agree:

- IAM allows the principal to call the needed AWS APIs.
- Lake Formation allows the principal to use the catalog resource, location, or
  underlying data.

That split is the source of most Lake Formation confusion. A principal can have
an IAM allow and still be blocked by Lake Formation. A principal can have a Lake
Formation grant and still fail because it lacks the IAM permission for the API
call.

`lfguard` manages the reviewable Lake Formation policy layer:

- LF-Tag keys and allowed values.
- LF-Tag assignments on Data Catalog resources.
- Lake Formation grants on named resources or LF-Tag policies.

`lfguard` does not create IAM roles, Glue databases, tables, S3 buckets,
registered locations, cross-account shares, data lake administrators, or row and
cell data filters.

## Use LF-Tags for Scale

Use named resource grants for small, stable exceptions. Use LF-Tag based access
control when access should follow durable business attributes such as:

- `domain=sales`
- `classification=internal`
- `environment=prod`
- `owner=data-platform`

The efficient pattern is:

1. Define a small LF-Tag vocabulary.
2. Assign LF-Tags to databases, tables, or columns.
3. Grant principals access through LF-Tag expressions.
4. Review drift and planned changes before applying anything.

This keeps policy growth closer to `principals + resources` instead of
`principals * resources`.

## LF-Tag Behavior to Remember

AWS stores LF-Tag keys and values in lower case. Write desired state in lower
case so reviews, snapshots, and plans do not fight case normalization.

Every LF-Tag key must be defined before it is assigned to a resource or used in
an LF-Tag expression. A key can have up to 1000 possible values, but a single
resource can have only one value for a given key and at most 50 assigned
LF-Tags.

Inheritance is useful, but explicit overrides matter. Tables inherit LF-Tags
from databases, and columns inherit LF-Tags from tables. Assigning the same key
lower in the hierarchy overrides the inherited value. Removing that explicit
assignment restores the inherited value.

Expression logic is simple but easy to misread. Multiple values for the same key
are OR. Multiple keys are AND. For example,
`domain=sales|finance AND classification=internal` matches sales or finance
resources that are also internal. In LF-Tag policy grants, AWS also supports
`*` as all values for a tag key.

Deleting LF-Tag values or whole LF-Tags is dangerous. AWS does not first check
whether the value or tag is still attached to Data Catalog resources. If the
deleted tag or value was driving a grant, the matching permissions disappear.

For the full tag and permission matrix, including column override examples and
permission combinations, see [`tag-permission-matrix.md`](tag-permission-matrix.md).

## Best Practices

- Keep IAM administration and Lake Formation policy review separate.
- Use read-only automation for snapshot, audit, plan, and report workflows.
- Use a separate additive apply role for creating LF-Tags, adding tag values,
  assigning tags, and granting permissions.
- Keep revokes and removals in a separate destructive maintenance workflow.
- Use stable, low-cardinality tag keys such as domain, classification,
  environment, and owner.
- Review `IAMAllowedPrincipals` before claiming Lake Formation is the source of
  truth.
- Use hybrid access mode only as an intentional migration or coexistence model.
- Capture scoped snapshots from desired state instead of dumping the whole
  account into CI artifacts.
- Store Markdown, JSON, or SARIF reports so reviewers can see what changed and
  why.

## Antipatterns

- Treating IAM allow policies as proof that Lake Formation access is correct.
- Treating Lake Formation grants as enough when the principal still lacks IAM
  API permissions.
- Leaving broad `IAMAllowedPrincipals` or `ALLIAMPrincipals` grants unreviewed.
- Using LF-Tags as free-form labels, ticket numbers, or table-specific aliases.
- Writing mixed-case LF-Tags and assuming AWS will preserve the case.
- Assigning multiple values for the same LF-Tag key to one resource.
- Encoding an OR rule as one LF-Tag expression that actually means AND.
- Deleting LF-Tag values without first checking resource assignments and grants.
- Putting `--allow-permission-revokes`, `--allow-resource-tag-removals`, or
  `--allow-lf-tag-value-removals` into routine CI.
- Assuming `lfguard snapshot` is full-account discovery.
- Modeling row or cell data filters in `lfguard` before the package supports
  them.

## Simple Rollout

1. Run `lfguard sample --output-dir lfguard-demo` and inspect the plan output.
2. Draft `policy/desired.json` with a small LF-Tag vocabulary.
3. Run `lfguard check --desired policy/desired.json --fail-on-findings`.
4. Capture a scoped non-production snapshot with `lfguard snapshot`.
5. Run `lfguard audit` and `lfguard plan` from that snapshot in CI.
6. Apply additive changes only after reviewing the plan.
7. Move revokes and tag removals to a separate approved workflow.

Start with the smallest workflow that answers today's question:

- Use `lfguard check` when you only need local policy validation.
- Use `lfguard audit` when you need to know whether current state drifted.
- Use `lfguard plan` when you need to review the exact changes before apply.
- Use `lfguard bootstrap --output-dir lfguard-policy` when you want a minimal
  starter repository.

Add optional bootstrap scaffolds only when they have an owner:

- `--include-live-drift`: scheduled AWS drift checks.
- `--include-code-scanning`: SARIF upload for repositories that already use Code
  Scanning dashboards.
- `--include-review-template`: CODEOWNERS and pull request review checklist.
- `--include-editor-config`: editor schema validation for policy authors.

## Source References

- [AWS Lake Formation permissions overview](https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-overview.html)
- [AWS Lake Formation permissions reference](https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-reference.html)
- [AWS Lake Formation personas and IAM permissions reference](https://docs.aws.amazon.com/lake-formation/latest/dg/permissions-reference.html)
- [IAM permissions required to grant or revoke Lake Formation permissions](https://docs.aws.amazon.com/lake-formation/latest/dg/required-permissions-for-grant.html)
- [Lake Formation tag-based access control](https://docs.aws.amazon.com/lake-formation/latest/dg/tag-based-access-control.html)
- [Creating LF-Tags](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-creating-tags.html)
- [Assigning LF-Tags to Data Catalog resources](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-assigning-tags.html)
- [Creating LF-Tag expressions](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-creating-tag-expressions.html)
- [Granting data lake permissions using LF-TBAC](https://docs.aws.amazon.com/lake-formation/latest/dg/granting-catalog-perms-TBAC.html)
- [LF-Tag best practices and considerations](https://docs.aws.amazon.com/lake-formation/latest/dg/lf-tag-considerations.html)
- [Deleting LF-Tags](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-deleting-tags.html)
- [Hybrid access mode](https://docs.aws.amazon.com/lake-formation/latest/dg/hybrid-access-mode.html)
- [Data filtering and cell-level security](https://docs.aws.amazon.com/lake-formation/latest/dg/data-filtering.html)
- [Updating LF-Tags](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-updating-tags.html)
