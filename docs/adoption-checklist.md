# Adoption Checklist

Use this checklist when introducing `lfguard` to a Lake Formation environment.
Start offline, then add CI, then decide whether controlled apply belongs in your
workflow.

## 1. Run the Offline Demo

Install the base package and generate sample files:

```bash
python -m pip install lfguard
lfguard sample --output-dir lfguard-demo
lfguard plan \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

This proves the CLI works without AWS credentials.

## 2. Draft Desired State

Create a starter policy and replace the example names with sanitized values from
your environment:

```bash
lfguard init --output-file policy/desired.json
```

Use JSON first unless your repository already standardizes on YAML. Add the YAML
extra when needed:

```bash
python -m pip install "lfguard[yaml]"
```

## 3. Validate Policy Shape

Run validation before connecting to AWS:

```bash
lfguard validate --desired policy/desired.json
```

Commit desired state only after principal names, database names, table names,
and LF-Tag values have passed your review rules.

## 4. Capture Current State

Install the AWS extra and capture a scoped snapshot from a non-production
environment first:

```bash
python -m pip install "lfguard[aws]"
lfguard snapshot \
  --desired policy/desired.json \
  --profile sandbox \
  --region us-east-1 \
  --output-file snapshots/sandbox-current.json
```

The snapshot scope comes from desired state, so review the desired file before
using it to read live AWS state.

## 5. Add CI Drift Checks

Use audit when drift should be visible as findings:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-findings \
  --output markdown \
  --output-file artifacts/lfguard-audit.md
```

Use plan when a non-empty change plan should block a merge:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-changes
```

## 6. Review Apply Behavior

Run live apply without `--execute` first. This is a dry run:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile sandbox \
  --region us-east-1 \
  --output markdown \
  --output-file artifacts/lfguard-apply-dry-run.md
```

Execute only after reviewing the plan and confirming the IAM/Lake Formation
permissions are intentionally scoped:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile sandbox \
  --region us-east-1 \
  --execute
```

## 7. Separate Destructive Changes

Keep revokes and removals on a separate approval path. They are omitted unless
explicitly allowed:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --allow-permission-revokes \
  --allow-resource-tag-removals \
  --allow-lf-tag-value-removals
```

## 8. Move to Production Carefully

Before production use, confirm:

- The desired-state file is reviewed and owned by the right platform or data
  governance team.
- CI stores audit, plan, or apply reports as artifacts.
- The AWS principal used by automation has only the needed read or apply
  permissions.
- Dry-run output is reviewed before any `--execute` run.
- Destructive flags are not enabled in routine additive workflows.

For operational examples, see [`recipes.md`](recipes.md),
[`safety-model.md`](safety-model.md), and
[`github-actions.md`](github-actions.md).
