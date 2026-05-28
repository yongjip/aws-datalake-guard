# GitHub Actions

This workflow runs `lfguard` against a checked-in desired policy and a generated
current-state snapshot. It is intended for platform repositories that already
use GitHub OIDC to assume an AWS role.

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

      - name: Export policy schema
        run: lfguard schema --output-file policy/lfguard.schema.json

      - name: Validate desired policy
        run: lfguard validate --desired policy/desired.yaml

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

`lfguard audit` writes the report file before returning a non-zero status for
`--fail-on-findings`, so the artifact upload step still has evidence to attach
when drift breaks the job.
