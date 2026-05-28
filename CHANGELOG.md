# Changelog

## 0.1.0

- Initial release of `lfguard`.
- Adds the `lfguard` CLI with `validate`, `audit`, `plan`, `snapshot`, and
  conservative `apply` commands.
- Adds importable planning and audit APIs under `lakeformation_guard`.
- Supports LF-Tag definitions, resource tag assignments, and Lake Formation grants.
- Includes an optional boto3 adapter for live AWS inventory and execution.
- Ships offline JSON/YAML desired-state workflows and example policy files.
