# GitHub Actions

This workflow runs `lfguard` against a checked-in desired policy and a generated
current-state snapshot. It is intended for platform repositories that already
use GitHub OIDC to assume an AWS role.

The same workflow is available as a copyable file at
[`examples/github-actions/lakeformation-drift.yml`](../examples/github-actions/lakeformation-drift.yml).
An optional Code Scanning variant is available at
[`examples/github-actions/lakeformation-code-scanning.yml`](../examples/github-actions/lakeformation-code-scanning.yml).

```yaml
name: Lake Formation drift

on:
  workflow_dispatch:
  schedule:
    - cron: "17 * * * *"

permissions:
  contents: read
  id-token: write

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::111122223333:role/LakeFormationReadOnly
          aws-region: ap-northeast-2

      - name: Install lfguard
        run: python -m pip install "lfguard[aws,yaml]"

      - name: Check lfguard install
        run: lfguard doctor --require aws --require yaml

      - name: Export policy schema
        run: lfguard schema --output-file policy/lfguard.schema.json

      - name: Validate desired policy
        run: lfguard validate --desired policy/desired.yaml

      - name: Lint desired policy
        run: |
          lfguard lint \
            --desired policy/desired.yaml \
            --output sarif \
            --output-file artifacts/lfguard-lint.sarif

          lfguard lint \
            --desired policy/desired.yaml \
            --fail-on-findings \
            --github-summary

      - name: Summarize policy
        run: |
          lfguard summary \
            --desired policy/desired.yaml \
            --output markdown \
            --output-file artifacts/lfguard-summary.md \
            --github-summary

      - name: Capture current state
        run: |
          lfguard snapshot \
            --desired policy/desired.yaml \
            --region ap-northeast-2 \
            --output-file snapshots/prod-current.json

      - name: Audit drift
        run: |
          lfguard audit \
            --desired policy/desired.yaml \
            --current-snapshot snapshots/prod-current.json \
            --output sarif \
            --output-file artifacts/lfguard-audit.sarif

          lfguard audit \
            --desired policy/desired.yaml \
            --current-snapshot snapshots/prod-current.json \
            --output markdown \
            --output-file artifacts/lfguard-audit.md \
            --fail-on-findings \
            --github-summary

      - name: Upload lfguard reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: lfguard-reports
          path: artifacts/
          if-no-files-found: ignore
          retention-days: 14
```

For pull requests from forks, avoid granting AWS credentials directly to the PR
workflow. A safer pattern is to run drift checks on a schedule, on manual
dispatch, or after changes are merged to a protected branch.

`lfguard lint` and `lfguard audit` write report files before returning a
non-zero status for `--fail-on-findings`, so the artifact upload step still has
evidence to attach when policy lint or drift checks break the job. The SARIF
artifacts can also be uploaded to systems that ingest static-analysis or
governance findings.

## GitHub Code Scanning

When a repository can upload SARIF to GitHub Code Scanning, use the copyable
[`lakeformation-code-scanning.yml`](../examples/github-actions/lakeformation-code-scanning.yml)
workflow. It:

- grants `security-events: write` for SARIF upload;
- writes separate `lfguard-lint` and `lfguard-audit` SARIF categories;
- uploads both SARIF files before enforcing the final lint and drift gates.

This keeps findings visible in the Security tab even when the final gate fails.
