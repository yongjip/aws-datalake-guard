# CLI Reference

`lfguard` installs two console commands:

- `lfguard`: the primary command.
- `aws-lakeformation-guard`: a descriptive alias for environments that prefer
  explicit command names.

Use `lfguard --help` or `lfguard <command> --help` for argparse-generated help.

## Command Overview

| Command | Purpose | AWS calls |
| --- | --- | --- |
| `init` | Generate a starter desired-state policy file. | No |
| `schema` | Emit the JSON Schema for desired/current state files. | No |
| `doctor` | Check the local install and optional extras. | No |
| `validate` | Parse and validate local desired/current state files. | No |
| `audit` | Report drift between desired and current state. | Only when `--current-snapshot` is omitted |
| `plan` | Produce a conservative change plan. | Only when `--current-snapshot` is omitted |
| `snapshot` | Export live AWS state for a desired policy scope. | Yes |
| `apply` | Dry-run or execute a Lake Formation change plan. | Yes when live state is loaded or `--execute` is used |

## Common Options

State-aware commands use these options:

- `--desired PATH`: desired state JSON/YAML file.
- `--current-snapshot PATH`: current state JSON/YAML file. When omitted,
  `audit`, `plan`, and `apply` load live AWS state through `boto3`.
- `--profile NAME`: AWS profile for live operations.
- `--region NAME`: AWS region for live operations.
- `--catalog-id ID`: Glue Data Catalog ID.
- `--output text|json|markdown`: output format where supported.
- `--output-file PATH`: write the command report to a file instead of stdout
  where supported.
- `--github-summary`: append a Markdown report to `$GITHUB_STEP_SUMMARY` where
  supported.

YAML files require the optional extra:

```bash
python -m pip install "lfguard[yaml]"
```

Live AWS commands require the AWS extra:

```bash
python -m pip install "lfguard[aws]"
```

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Command completed successfully. |
| `1` | A CI gate failed, such as `audit --fail-on-findings` or `plan --fail-on-changes`. |
| `2` | CLI usage, file format, validation, or runtime configuration error. |

Report files and GitHub summaries are written before `audit --fail-on-findings`
or `plan --fail-on-changes` return exit code `1`.

## `init`

Generate a starter desired policy:

```bash
lfguard init --output-file policy/desired.json
```

Useful options:

- `--output-file PATH`: write the starter policy to a file.
- `--format json|yaml`: force the output format.
- `--force`: overwrite an existing output file.

When `--format` is omitted, `.yaml` and `.yml` output paths produce YAML;
stdout defaults to JSON.

## `schema`

Write the JSON Schema for editor integration or CI validation:

```bash
lfguard schema --output-file policy/lfguard.schema.json
```

## `doctor`

Check the install, Python runtime, optional dependencies, and AWS-related
environment variables without making AWS calls:

```bash
lfguard doctor
lfguard doctor --output json
```

## `validate`

Validate local policy files:

```bash
lfguard validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

`validate` does not call AWS. Use it in pre-commit hooks or CI before comparing
against live state.

## `audit`

Report drift between desired and current state:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

CI-friendly audit:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output json \
  --output-file artifacts/lfguard-audit.json \
  --fail-on-findings
```

Useful options:

- `--fail-on-findings`: return exit code `1` when any finding exists.
- `--github-summary`: append a Markdown audit report to the GitHub Actions job
  summary.

## `plan`

Produce a conservative change plan:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

By default, the plan includes additive changes only. Destructive changes are
omitted unless the matching allow flag is set.

CI-friendly plan gate:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output markdown \
  --output-file artifacts/lfguard-plan.md \
  --fail-on-changes
```

Destructive planning flags:

- `--allow-lf-tag-value-removals`
- `--allow-resource-tag-removals`
- `--allow-permission-revokes`

## `snapshot`

Export live AWS state for the resources and principals referenced by the desired
policy:

```bash
lfguard snapshot \
  --desired policy/desired.yaml \
  --profile prod \
  --region ap-northeast-2 \
  --output-file snapshots/prod-current.json
```

`snapshot` uses the desired policy as the scope so it does not attempt to
inventory an entire account.

## `apply`

Dry-run by default:

```bash
lfguard apply \
  --desired policy/desired.yaml \
  --profile prod \
  --region ap-northeast-2
```

Save the dry-run report:

```bash
lfguard apply \
  --desired policy/desired.yaml \
  --profile prod \
  --region ap-northeast-2 \
  --output markdown \
  --output-file artifacts/lfguard-apply-dry-run.md
```

Execute additive changes:

```bash
lfguard apply \
  --desired policy/desired.yaml \
  --profile prod \
  --region ap-northeast-2 \
  --execute
```

Save executed results:

```bash
lfguard apply \
  --desired policy/desired.yaml \
  --profile prod \
  --region ap-northeast-2 \
  --execute \
  --output json \
  --output-file artifacts/lfguard-apply.json
```

Even during execution, destructive changes require the same explicit allow flags
used by `plan`.
