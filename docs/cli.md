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
| `bootstrap` | Create a starter policy repository layout with CI and pre-commit files. | No |
| `sample` | Generate offline demo desired/current state files. | No |
| `schema` | Emit the JSON Schema for desired/current state files. | No |
| `doctor` | Check the local install and optional extras. | No |
| `permissions` | Emit starter IAM policies for live AWS workflows. | No |
| `validate` | Parse and validate local desired/current state files. | No |
| `lint` | Check desired policy semantics, such as undefined LF-Tag references. | No |
| `summary` | Summarize desired and optional current state for review. | No |
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
- `--output text|json|markdown|sarif`: output format where supported. `audit`
  and `lint` support SARIF; `permissions`, `lint`, `summary`, `audit`, `plan`,
  and `apply` support Markdown.
- `--output-file PATH`: write the command report to a file instead of stdout
  where supported. `doctor`, `permissions`, `validate`, `lint`, `summary`,
  `audit`, `plan`, and `apply` support this for reports; `init`, `schema`, and
  `snapshot` use it for generated files.
- `--github-summary`: append a Markdown report to `$GITHUB_STEP_SUMMARY` where
  supported.

See [`state-format.md`](state-format.md) for desired/current state examples for
each supported Lake Formation resource kind.

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

Report files and GitHub summaries are written before `lint --fail-on-findings`,
`audit --fail-on-findings`, or `plan --fail-on-changes` return exit code `1`.

See [`report-formats.md`](report-formats.md) for JSON and Markdown payload
examples for audit, plan, and apply reports.

## `init`

Generate a starter desired policy:

```bash
lfguard init --output-file policy/desired.json
```

Useful options:

- `--output-file PATH`: write the starter policy to a file.
- `--format json|yaml`: force the output format.
- `--template data-domain|blank`: choose the starter policy. `data-domain`
  includes example LF-Tags, one table tag assignment, and one LF-Tag policy
  grant. `blank` writes an empty valid policy skeleton.
- `--force`: overwrite an existing output file.

When `--format` is omitted, `.yaml` and `.yml` output paths produce YAML;
stdout defaults to JSON.

```bash
lfguard init --template blank --output-file policy/desired.json
```

## `bootstrap`

Create a starter policy repository layout:

```bash
lfguard bootstrap --output-dir lfguard-policy
```

The generated layout includes:

- `policy/desired.json`: starter desired LF-Tag and grant policy.
- `policy/lfguard.schema.json`: JSON Schema for editor integration.
- `.github/workflows/lfguard-policy.yml`: offline validation, lint, summary,
  and artifact workflow.
- `.pre-commit-config.yaml`: local validate and lint hooks.
- `README.md`: rollout steps and first commands.

Useful options:

- `--format json|yaml`: choose the desired policy file format. YAML workflows
  install `lfguard[yaml]`.
- `--template data-domain|blank`: choose the starter policy.
- `--force`: overwrite existing bootstrap files.

## `sample`

Generate paired offline demo files that work immediately after `pip install`:

```bash
lfguard sample --output-dir lfguard-demo --include-ci
lfguard plan \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

Useful options:

- `--output-dir PATH`: directory to write `desired.json` and
  `current-snapshot.json`, plus a local `README.md` with demo commands.
- `--format json|yaml|both`: choose JSON sample files, YAML sample files, or
  both. YAML files require `lfguard[yaml]` when read by later commands.
- `--include-ci`: also write `.github/workflows/lfguard-demo.yml`, an offline
  GitHub Actions workflow that validates, lints, audits, plans, and uploads
  report artifacts for the generated sample files.
- `--force`: overwrite existing sample files.

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
lfguard doctor --require aws --require yaml
lfguard doctor --output json --output-file artifacts/lfguard-doctor.json
```

Use `--require aws` or `--require yaml` to return exit code `1` when a needed
optional extra is missing. Repeat `--require` to check multiple extras.

## `permissions`

Generate starter IAM policies for live `snapshot`, `audit`, `plan`, and
`apply` workflows:

```bash
lfguard permissions --template read-only --output-file iam/lfguard-read-only.json
lfguard permissions --template additive-apply --include-glue-read
lfguard permissions --template destructive-apply --output markdown
```

Useful options:

- `--template read-only|additive-apply|destructive-apply`: choose the IAM
  policy template. `additive-apply` omits revoke and tag-removal actions;
  `destructive-apply` includes them for separately reviewed workflows.
- `--include-glue-read`: add common Glue Data Catalog read actions.
- `--output text|json|markdown`: choose raw JSON or a Markdown report. Text and
  JSON both emit copyable IAM policy JSON.
- `--output-file PATH`: write the policy to a file instead of stdout.

## `validate`

Validate local policy files:

```bash
lfguard validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

`validate` does not call AWS. Use it in pre-commit hooks or CI before comparing
against live state.

```bash
lfguard validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output-file artifacts/lfguard-validate.txt
```

## `lint`

Lint desired policy for semantic issues that parse-time validation cannot catch:

```bash
lfguard lint --desired policy/desired.json
```

`lint` does not call AWS. It catches undefined LF-Tag keys and values used in
resource tag assignments and LF-Tag policy expressions. It also warns when a
desired policy is empty.

CI-friendly lint gate:

```bash
lfguard lint \
  --desired policy/desired.json \
  --output json \
  --output-file artifacts/lfguard-lint.json \
  --fail-on-findings \
  --github-summary
```

Useful options:

- `--fail-on-findings`: return exit code `1` when any lint finding exists.
- `--fail-on-severity any|error`: severity that triggers `--fail-on-findings`.
  Use `error` when warnings should stay visible but should not fail CI.
- `--output sarif`: write lint findings as SARIF 2.1.0 for code scanning,
  governance dashboards, or artifact ingestion.

## `summary`

Summarize policy inventory without calling AWS:

```bash
lfguard summary \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

Use it in pull requests when reviewers need a compact view of LF-Tag keys,
resource kinds, grant principals, grant resource kinds, and permissions:

```bash
lfguard summary \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output markdown \
  --output-file artifacts/lfguard-summary.md \
  --github-summary
```

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

- Audit text, JSON, and Markdown output include a severity summary. JSON reports
  expose `summary.total`, `summary.errors`, and `summary.warnings`.
- `--output sarif`: write audit findings as SARIF 2.1.0 for code scanning,
  governance dashboards, or artifact ingestion.
- `--fail-on-findings`: return exit code `1` when any finding exists.
- `--fail-on-severity any|error`: severity that triggers `--fail-on-findings`.
  The default is `any`, which preserves strict drift gates. Use `error` when
  unmanaged extras should remain visible warnings but not fail CI.
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
