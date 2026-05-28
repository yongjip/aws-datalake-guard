# Changelog

## 0.1.0

- Initial release of `lfguard`.
- Adds the `lfguard` CLI with `init`, `schema`, `check`, `validate`, `lint`,
  `audit`, `plan`, `sample`, `bootstrap`, `doctor`, `permissions`,
  `completion`, `snapshot`, and conservative `apply` commands.
- Adds desired-policy lint checks for undefined LF-Tag keys and values.
- Adds a `check` command for one-step offline validation and lint gates.
- Uses `check` in generated policy/demo workflows and release smoke tests.
- Emphasizes `check` in first-run quickstarts before planning changes.
- Adds policy summary reports for compact review of desired and current state.
- Adds text, JSON, and Markdown output for reviewable audit and plan workflows.
- Adds SARIF output for audit and lint findings.
- Adds an offline install check for optional AWS and YAML integrations.
- Adds `doctor --require` checks for failing CI when required optional extras
  are missing.
- Adds a `permissions` command for generating starter IAM policies for
  read-only, additive apply, and destructive apply workflows.
- Adds a `completion` command for bash, zsh, and fish shell completions.
- Adds a `--github-summary` option for GitHub Actions job summaries across
  lint, summary, audit, plan, and apply workflows.
- Adds a copyable GitHub Code Scanning workflow for lint and audit SARIF
  uploads.
- Adds a `--fail-on-changes` option for CI plan gates.
- Adds a `--fail-on-severity` option for error-only audit gates.
- Adds severity summaries to audit text, JSON, and Markdown reports.
- Adds `--output-file` report capture for audit, plan, and apply workflows.
- Adds `--output-file` diagnostics capture for doctor and validate workflows.
- Documents GitHub Actions report artifact uploads and preserves CI build artifacts.
- Adds a CLI reference with command semantics, common options, and exit codes.
- Adds YAML starter policy generation and a YAML example policy.
- Adds `init --template` starter policies for a data-domain example or blank
  policy skeleton.
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
- Calls out README scope limits early so new users can evaluate fit quickly.
- Adds a README capability matrix for quick PyPI-page evaluation.
- Adds a troubleshooting guide for common install, AWS, planning, and CI issues.
- Adds GitHub issue and pull request templates for safer community reports.
- Adds a copyable GitHub Actions drift-check workflow under `examples/`.
- Adds a copyable pre-commit validation hook example under `examples/`.
- Adds an architecture guide for package boundaries, data flow, and AWS adapter
  responsibilities.
- Adds a roadmap with near-term priorities, evaluation questions, and non-goals.
- Adds publish-ready release notes for the first public PyPI release.
- Documents `pipx` and `uv tool` install paths for CLI users.
- Adds a `sample` command for generating a runnable offline demo after install,
  including a local README with copy-paste commands.
- Adds `sample --include-ci` for generating an offline GitHub Actions demo
  workflow alongside the sample files.
- Adds a `bootstrap` command for generating a starter policy repository layout
  with schema, CI, pre-commit, and rollout README files.
- Adds JSON, YAML, and combined output formats for generated sample demos.
- Adds a state-format guide with examples for each supported resource kind.
- Adds an AWS API coverage guide for live inventory and apply calls.
- Adds an FAQ for safety, scope, credentials, and adoption questions.
- Adds CI and release workflow smoke tests for the built wheel.
- Adds docs tests for internal Markdown links.
- Adds package metadata tests for version, console scripts, and project URLs.
- Modernizes the build backend requirement for current setuptools releases.
- Uses SPDX license metadata without deprecated license classifiers.
