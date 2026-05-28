# Changelog

## 0.1.0

- Initial release of `lfguard`.
- Adds the `lfguard` CLI with `init`, `schema`, `validate`, `audit`, `plan`,
  `sample`, `doctor`, `snapshot`, and conservative `apply` commands.
- Adds text, JSON, and Markdown output for reviewable audit and plan workflows.
- Adds an offline install check for optional AWS and YAML integrations.
- Adds a `--github-summary` option for GitHub Actions job summaries.
- Adds a `--fail-on-changes` option for CI plan gates.
- Adds a `--fail-on-severity` option for error-only audit gates.
- Adds severity summaries to audit text, JSON, and Markdown reports.
- Adds `--output-file` report capture for audit, plan, and apply workflows.
- Adds `--output-file` diagnostics capture for doctor and validate workflows.
- Documents GitHub Actions report artifact uploads and preserves CI build artifacts.
- Adds a CLI reference with command semantics, common options, and exit codes.
- Adds YAML starter policy generation and a YAML example policy.
- Ships a JSON Schema for desired/current state files.
- Adds importable planning and audit APIs under `lakeformation_guard`.
- Supports LF-Tag definitions, resource tag assignments, and Lake Formation grants.
- Includes an optional boto3 adapter for live AWS inventory and execution.
- Ships offline JSON/YAML desired-state workflows and example policy files.
- Adds an examples guide and PyPI metadata links for first-run discoverability.
- Adds an adoption checklist for moving from offline demo to CI and controlled
  apply workflows.
- Adds a report-format guide for audit, plan, apply, and CI artifacts.
- Adds a safety model guide for conservative defaults and destructive changes.
- Adds a positioning guide for how `lfguard` fits with infrastructure tools,
  raw boto3, and console workflows.
- Adds a troubleshooting guide for common install, AWS, planning, and CI issues.
- Adds GitHub issue and pull request templates for safer community reports.
- Adds a copyable GitHub Actions drift-check workflow under `examples/`.
- Adds a copyable pre-commit validation hook example under `examples/`.
- Adds an architecture guide for package boundaries, data flow, and AWS adapter
  responsibilities.
- Adds a roadmap with near-term priorities, evaluation questions, and non-goals.
- Adds a `sample` command for generating a runnable offline demo after install,
  including a local README with copy-paste commands.
- Adds JSON, YAML, and combined output formats for generated sample demos.
- Adds a state-format guide with examples for each supported resource kind.
- Adds an AWS API coverage guide for live inventory and apply calls.
- Adds an FAQ for safety, scope, credentials, and adoption questions.
- Adds CI and release workflow smoke tests for the built wheel.
- Adds docs tests for internal Markdown links.
- Adds package metadata tests for version, console scripts, and project URLs.
- Modernizes the build backend requirement for current setuptools releases.
- Uses SPDX license metadata without deprecated license classifiers.
