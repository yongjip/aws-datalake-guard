# Examples

These files let you try `lfguard` without AWS credentials:

- `desired.json`: a desired Lake Formation LF-Tag and grant policy.
- `desired.yaml`: the same desired policy in YAML.
- `current-snapshot.json`: a deliberately incomplete current-state snapshot.

The snapshot is missing two desired LF-Tag values, one table tag assignment, and
one LF-Tag policy grant. That makes it useful for seeing audit findings and
conservative plans.

## Validate the Policy

```bash
lfguard validate \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

This command only reads local files. It should report one LF-Tag definition set,
one resource tag assignment, and one grant in the desired policy.

## Audit Drift

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

Expected summary:

```text
Findings: 3.
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
