# Examples

These files let you try `lfguard` without AWS credentials:

- `desired.json`: a desired Lake Formation LF-Tag and grant policy.
- `desired.yaml`: the same desired policy in YAML.
- `current-snapshot.json`: a deliberately incomplete current-state snapshot.
- `github-actions/lakeformation-drift.yml`: a copyable GitHub Actions workflow
  for scheduled or manually dispatched drift checks against live AWS state.
- `github-actions/lakeformation-code-scanning.yml`: a copyable GitHub Actions
  workflow that uploads lint and audit SARIF reports to GitHub Code Scanning.
- `pre-commit/pre-commit-config.yaml`: a copyable local pre-commit hook that
  validates and lints a desired-state policy before commit.

The snapshot is missing two desired LF-Tag values, one table tag assignment, and
one LF-Tag policy grant. That makes it useful for seeing audit findings and
conservative plans.

If you installed `lfguard` from PyPI and do not have this repository checked
out, generate the same kind of local demo files with:

```bash
lfguard sample --output-dir lfguard-demo
```

## Validate the Policy

```bash
lfguard validate \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

This command only reads local files. It should report one LF-Tag definition set,
one resource tag assignment, and one grant in the desired policy.

## Lint the Policy

```bash
lfguard lint --desired examples/desired.json
```

This command only reads the desired policy. It catches undefined LF-Tag keys and
values in resource tag assignments and LF-Tag policy expressions before a CI job
captures live AWS state.

## Summarize the Policy

```bash
lfguard summary \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

This produces a compact inventory of LF-Tag keys, resource kinds, grant
principals, grant resource kinds, and permissions for reviewers.

## Audit Drift

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

Expected summary:

```text
Findings: 3 total, 3 error(s), 0 warning(s).
```

To use the audit in CI and save evidence for review:

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output json \
  --output-file artifacts/lfguard-audit.json \
  --fail-on-findings
```

The command writes `artifacts/lfguard-audit.json` before exiting with status `1`.

Use `--fail-on-severity error` when warnings should be reported but should not
fail the job:

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --fail-on-findings \
  --fail-on-severity error
```

## Plan Safe Changes

```bash
lfguard plan \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

Expected summary:

```text
Plan: 3 change(s), 3 safe, 0 destructive.
```

To save a Markdown plan for pull request review:

```bash
lfguard plan \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output markdown \
  --output-file artifacts/lfguard-plan.md
```

By default, the plan is additive only. It will add missing LF-Tag values,
resource tag assignments, and permissions, but it will not revoke permissions or
remove tag values unless a matching `--allow-*` flag is supplied.

## Try YAML

Install the YAML extra, then run the same plan against the YAML desired policy:

```bash
python -m pip install "lfguard[yaml]"
lfguard plan \
  --desired examples/desired.yaml \
  --current-snapshot examples/current-snapshot.json
```

## Copy a GitHub Actions Workflow

Use [`github-actions/lakeformation-drift.yml`](github-actions/lakeformation-drift.yml)
as a starting point when your policy repository already uses GitHub OIDC to
assume an AWS role. Replace the example role ARN, region, and policy paths
before enabling the workflow.

Use [`github-actions/lakeformation-code-scanning.yml`](github-actions/lakeformation-code-scanning.yml)
when your repository can upload SARIF to GitHub Code Scanning. It uploads
separate `lfguard-lint` and `lfguard-audit` categories before enforcing the lint
and drift gates.

## Copy a Pre-Commit Hook

Use [`pre-commit/pre-commit-config.yaml`](pre-commit/pre-commit-config.yaml) as
a starting point when developers should validate and lint desired-state policy
before committing. Copy it to `.pre-commit-config.yaml`, update the policy path,
and install the hook in an environment where `lfguard` is available:

```bash
python -m pip install lfguard pre-commit
pre-commit install
pre-commit run --all-files
```
