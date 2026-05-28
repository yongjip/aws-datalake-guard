# lfguard

[![CI](https://github.com/yongjip/aws-datalake-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/yongjip/aws-datalake-guard/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/lfguard.svg)](https://pypi.org/project/lfguard/)
[![Python](https://img.shields.io/pypi/pyversions/lfguard.svg)](https://pypi.org/project/lfguard/)

`lfguard` is an opinionated Python package for AWS Lake Formation
and Glue Data Catalog guardrails. It compares a desired LF-Tag and permission
policy against current state, reports drift, produces a conservative change plan,
and can apply only the changes that you explicitly allow.

The import package is `lakeformation_guard`; the primary CLI command is
`lfguard`. The package also installs `aws-lakeformation-guard` as a descriptive
command alias.

## What it manages

- LF-Tag definitions and allowed values.
- LF-Tag assignments on Lake Formation Data Catalog resources.
- Lake Formation grants on catalog, database, table, column, data location, and
  LF-Tag policy resources.
- Offline audit and plan workflows from JSON or YAML snapshots.
- Live AWS inventory and apply workflows through the optional `boto3` adapter.

By default, plans only add missing definitions, tag assignments, and permissions.
Potentially destructive changes, such as revoking permissions or removing tag
values, are omitted unless the matching allow flag is set.

## Why use it

- Reviewable plans before touching production Lake Formation state.
- Conservative defaults that avoid accidental revokes and tag removals.
- Works offline from snapshots, which makes CI drift checks possible.
- Keeps the Python API dependency-light while isolating boto3 in the AWS adapter.
- Produces text, JSON, and Markdown output suitable for pull request comments,
  release checks, and platform automation.

## Common use cases

- Fail a CI check when production Lake Formation state drifts from a reviewed
  desired-state file.
- Generate a safe change plan for new LF-Tag values, table tag assignments, and
  LF-Tag policy grants.
- Let platform teams review destructive operations separately from additive
  changes.
- Keep data access policy as code without writing direct boto3 orchestration for
  every grant and tag assignment.

## Install

```bash
python -m pip install lfguard
```

For live AWS usage:

```bash
python -m pip install "lfguard[aws]"
```

For YAML policy files:

```bash
python -m pip install "lfguard[yaml]"
```

## Quickstart

Check the local install and optional extras without making AWS calls:

```bash
lfguard doctor
```

Generate a runnable offline demo with no AWS credentials:

```bash
lfguard sample --output-dir lfguard-demo
```

The command writes `desired.json`, `current-snapshot.json`, and a short
`README.md` with copy-paste commands.

Plan against the generated desired state and deliberately incomplete snapshot:

```bash
lfguard plan \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

Expected output:

```text
Plan: 3 change(s), 3 safe, 0 destructive.
- [safe] lf_tag.add_values lf_tag:sensitivity: LF-Tag is missing allowed values
- [safe] resource_tag.add_values table:database=analytics:table=orders: Resource is missing desired LF-Tag assignments
- [safe] grant.add_permissions arn:aws:iam::111122223333:role/Analyst -> lf_tag_policy:resource_type=TABLE:expression=domain=sales,sensitivity=internal|public: Principal is missing desired Lake Formation permissions
```

## Desired state format

JSON and YAML use the same shape:

```json
{
  "lf_tags": {
    "sensitivity": ["public", "internal", "restricted"],
    "domain": ["sales", "finance"]
  },
  "resource_tags": [
    {
      "resource": {
        "kind": "table",
        "database": "analytics",
        "table": "orders"
      },
      "tags": {
        "sensitivity": ["internal"],
        "domain": ["sales"]
      }
    }
  ],
  "grants": [
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
  ]
}
```

Supported resource kinds are `catalog`, `database`, `table`,
`table_with_columns`, `data_location`, and `lf_tag_policy`.
See [`docs/state-format.md`](docs/state-format.md) for copyable examples of
each resource kind and grant shape.

## CLI

Show version and command help:

```bash
lfguard --version
lfguard --help
```

Create a starter desired-state file:

```bash
lfguard init --output-file policy/desired.json
```

Generate paired offline sample files for a local demo:

```bash
lfguard sample --output-dir lfguard-demo
```

Generate a YAML starter when your policy repo uses YAML:

```bash
lfguard init --output-file policy/desired.yaml
```

Check whether optional AWS/YAML integrations are installed:

```bash
lfguard doctor --output json
```

Save the install check for CI diagnostics:

```bash
lfguard doctor --output json --output-file artifacts/lfguard-doctor.json
```

Export the JSON Schema for editor or CI validation:

```bash
lfguard schema --output-file policy/lfguard.schema.json
```

Validate policy files without AWS credentials:

```bash
lfguard validate \
  --desired desired.json \
  --current-snapshot current.json
```

Save a validation report:

```bash
lfguard validate \
  --desired desired.json \
  --current-snapshot current.json \
  --output-file artifacts/lfguard-validate.txt
```

Plan against an offline snapshot:

```bash
lfguard plan \
  --desired desired.json \
  --current-snapshot current.json
```

Fail CI when the plan is not empty:

```bash
lfguard plan \
  --desired desired.json \
  --current-snapshot current.json \
  --fail-on-changes
```

Save a reviewable plan report as a CI artifact:

```bash
lfguard plan \
  --desired desired.json \
  --current-snapshot current.json \
  --output markdown \
  --output-file artifacts/lfguard-plan.md
```

Audit and fail the command when drift is found:

```bash
lfguard audit \
  --desired desired.json \
  --current-snapshot current.json \
  --fail-on-findings
```

Fail only when error-severity findings are present:

```bash
lfguard audit \
  --desired desired.json \
  --current-snapshot current.json \
  --fail-on-findings \
  --fail-on-severity error
```

Write a machine-readable audit report:

```bash
lfguard audit \
  --desired desired.json \
  --current-snapshot current.json \
  --output json \
  --output-file artifacts/lfguard-audit.json
```

Audit JSON includes `summary.total`, `summary.errors`, and `summary.warnings`
so CI jobs can show drift counts without parsing individual findings.

Use Markdown output for pull request comments or GitHub Actions summaries:

```bash
lfguard plan \
  --desired desired.json \
  --current-snapshot current.json \
  --output markdown
```

In GitHub Actions, append the Markdown report directly to the job summary:

```bash
lfguard audit \
  --desired desired.json \
  --current-snapshot current.json \
  --fail-on-findings \
  --github-summary
```

Export a live current-state snapshot for the resources and principals referenced
by a desired-state file:

```bash
lfguard snapshot \
  --desired desired.yaml \
  --profile prod \
  --region ap-northeast-2 \
  --output-file snapshots/prod-current.json
```

Dry-run against live AWS state:

```bash
lfguard apply \
  --desired desired.yaml \
  --profile prod \
  --region ap-northeast-2
```

Save the dry-run report before executing:

```bash
lfguard apply \
  --desired desired.yaml \
  --profile prod \
  --region ap-northeast-2 \
  --output markdown \
  --output-file artifacts/lfguard-apply-dry-run.md
```

Execute non-destructive changes:

```bash
lfguard apply \
  --desired desired.yaml \
  --profile prod \
  --region ap-northeast-2 \
  --execute
```

Save machine-readable apply results:

```bash
lfguard apply \
  --desired desired.yaml \
  --profile prod \
  --region ap-northeast-2 \
  --execute \
  --output json \
  --output-file artifacts/lfguard-apply.json
```

Allow revokes only when that is the intended maintenance operation:

```bash
lfguard plan \
  --desired desired.json \
  --current-snapshot current.json \
  --allow-permission-revokes
```

## Python API

```python
from lakeformation_guard import DesiredState, CurrentState, PlanOptions, audit, plan

desired = DesiredState.from_dict({
    "lf_tags": {"sensitivity": ["public", "internal"]},
    "grants": [
        {
            "principal": "arn:aws:iam::111122223333:role/Analyst",
            "resource": {"kind": "database", "database": "analytics"},
            "permissions": ["DESCRIBE"],
        }
    ],
})

current = CurrentState.empty()
findings = audit(desired, current)
change_plan = plan(desired, current, PlanOptions())

for finding in findings:
    print(finding.code, finding.message)

for change in change_plan.changes:
    print(change.action, change.target)
```

## Live AWS apply

The live adapter only depends on `boto3` when you instantiate it:

```python
from lakeformation_guard import DesiredState, PlanOptions, plan
from lakeformation_guard.aws import AWSLakeFormationAdapter

desired = DesiredState.from_file("desired.yaml")
adapter = AWSLakeFormationAdapter.from_boto3(profile_name="prod", region_name="ap-northeast-2")
current = adapter.load_current_state_for(desired)
change_plan = plan(desired, current, PlanOptions())
adapter.apply(change_plan, dry_run=False)
```

Use an IAM principal with the minimum Lake Formation permissions required for the
actions you intend to run. The package does not bypass AWS authorization and does
not turn destructive changes on by default.

## Release and Trust

The repository includes GitHub Actions for CI and PyPI Trusted Publishing. See
[`docs/publishing.md`](docs/publishing.md) for the release path and the exact
PyPI publisher settings.

## More docs

- [`docs/cli.md`](docs/cli.md): command reference, common options, and exit
  codes.
- [`docs/recipes.md`](docs/recipes.md): audit-only, CI, and controlled apply
  workflows.
- [`docs/report-formats.md`](docs/report-formats.md): JSON and Markdown report
  shapes for audits, plans, applies, and CI artifacts.
- [`docs/safety-model.md`](docs/safety-model.md): conservative defaults,
  destructive-change flags, apply behavior, and production patterns.
- [`docs/state-format.md`](docs/state-format.md): desired/current state file
  shape with examples for each supported resource kind.
- [`docs/schema.json`](docs/schema.json): JSON Schema for desired/current state
  files.
- [`docs/aws-api-coverage.md`](docs/aws-api-coverage.md): exact boto3 Lake
  Formation calls used for live inventory and apply.
- [`docs/github-actions.md`](docs/github-actions.md): a copy-paste drift check
  workflow using GitHub OIDC, job summaries, and uploaded report artifacts.
- [`docs/aws-permissions.md`](docs/aws-permissions.md): suggested minimum IAM
  permissions for read-only and apply roles.
- [`examples/README.md`](examples/README.md): offline files and commands for a
  first local audit/plan run.

## Development

```bash
python -m pip install -e ".[dev,aws,yaml]"
python -m unittest discover -s tests
python -m build
```
