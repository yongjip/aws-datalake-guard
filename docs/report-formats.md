# Report Formats

`lfguard` reports are designed for both humans and CI systems. Commands that
support reports accept `--output text`, `--output json`, or `--output markdown`
where appropriate, and `--output-file PATH` writes the same report without
printing to stdout.

## Audit Reports

Use audit reports when you want to detect drift without proposing or applying
changes.

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output json
```

JSON audit reports contain a severity summary and an ordered list of findings:

```json
{
  "summary": {
    "total": 3,
    "errors": 3,
    "warnings": 0
  },
  "findings": [
    {
      "code": "LF_TAG_VALUES_MISSING",
      "severity": "error",
      "target": "lf_tag:sensitivity",
      "message": "Desired LF-Tag values are missing",
      "details": {
        "tag_key": "sensitivity",
        "missing_values": ["internal", "restricted"]
      }
    }
  ]
}
```

Finding severities have these meanings:

- `error`: desired state is missing from current state and should usually block
  CI when `--fail-on-findings` is used.
- `warning`: current state contains unmanaged extras. Use
  `--fail-on-severity error` when warnings should remain visible but should not
  fail CI.

Markdown audit reports use the same finding order and include summary counts,
which makes them suitable for GitHub Actions job summaries:

```markdown
### lfguard audit

- Total findings: 3
- Error findings: 3
- Warning findings: 0

| Severity | Code | Target | Message |
| --- | --- | --- | --- |
| error | LF_TAG_VALUES_MISSING | lf_tag:sensitivity | Desired LF-Tag values are missing |
```

## Plan Reports

Use plan reports when you want a reviewable change list before touching AWS.

```bash
lfguard plan \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output json
```

JSON plan reports contain a safety summary and an ordered list of proposed
changes:

```json
{
  "summary": {
    "total": 3,
    "safe": 3,
    "destructive": 0
  },
  "changes": [
    {
      "action": "lf_tag.add_values",
      "target": "lf_tag:sensitivity",
      "reason": "LF-Tag is missing allowed values",
      "destructive": false,
      "payload": {
        "tag_key": "sensitivity",
        "tag_values": ["internal", "restricted"]
      }
    }
  ]
}
```

Plan safety has these meanings:

- `safe`: additive changes, such as creating missing LF-Tags, adding missing tag
  values, adding resource tag assignments, or adding permissions.
- `destructive`: removals or revokes. These are omitted by default and appear
  only when a matching `--allow-*` planning flag is supplied.

Markdown plan reports include the same safety summary and change list for pull
request review.

## Apply Reports

`lfguard apply` defaults to dry-run mode and renders the computed plan. With
`--execute --output json`, the report includes the plan plus per-change execution
results:

```json
{
  "plan": {
    "summary": {
      "total": 1,
      "safe": 1,
      "destructive": 0
    },
    "changes": [
      {
        "action": "lf_tag.create",
        "target": "lf_tag:sensitivity",
        "reason": "LF-Tag is missing",
        "destructive": false,
        "payload": {
          "tag_key": "sensitivity",
          "tag_values": ["internal"]
        }
      }
    ]
  },
  "results": [
    {
      "action": "lf_tag.create",
      "target": "lf_tag:sensitivity",
      "applied": true,
      "response": {}
    }
  ]
}
```

Even with `--execute`, destructive changes are applied only when the matching
allow flag is present.

## GitHub Actions

For pull requests, combine machine-readable artifacts with a readable job
summary:

```bash
lfguard audit \
  --desired policy/desired.yaml \
  --current-snapshot snapshots/prod-current.json \
  --output json \
  --output-file artifacts/lfguard-audit.json \
  --fail-on-findings \
  --github-summary
```

The report file is written before CI gate flags return exit code `1`, so failed
jobs still leave evidence for review.
