# Changelog

## 0.1.0

- Initial release of `lfguard`.
- Adds the `lfguard` CLI with `init`, `schema`, `validate`, `audit`, `plan`,
  `doctor`, `snapshot`, and conservative `apply` commands.
- Adds text, JSON, and Markdown output for reviewable audit and plan workflows.
- Adds an offline install check for optional AWS and YAML integrations.
- Adds a `--github-summary` option for GitHub Actions job summaries.
- Adds YAML starter policy generation and a YAML example policy.
- Ships a JSON Schema for desired/current state files.
- Adds importable planning and audit APIs under `lakeformation_guard`.
- Supports LF-Tag definitions, resource tag assignments, and Lake Formation grants.
- Includes an optional boto3 adapter for live AWS inventory and execution.
- Ships offline JSON/YAML desired-state workflows and example policy files.
