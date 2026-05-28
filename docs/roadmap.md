# Roadmap

This roadmap is intentionally conservative. `lfguard` should stay small,
reviewable, and safe by default while it expands around real Lake Formation
policy workflows.

## 0.1.0 Scope

The first release focuses on the core guardrail loop:

- Offline desired/current state files in JSON and optional YAML.
- Importable `lint_desired()`, `audit()`, and `plan()` APIs.
- A short `lfguard` CLI with validation, lint, audit, plan, snapshot, and apply
  workflows.
- Conservative planning defaults that omit revokes and removals unless explicitly
  allowed.
- Optional boto3 integration for scoped Lake Formation inventory and execution.
- Text, JSON, Markdown, and SARIF reports for local review and CI artifacts.

## Near-Term Priorities

The most useful next improvements are:

- More real-world examples for LF-Tag policy grants, table-with-columns grants,
  and data location permissions.
- Better validation messages that point directly at the problematic field in a
  desired-state file.
- Additional report examples for pull request comments and scheduled governance
  reviews.
- More adapter tests around AWS pagination, not-found handling, and destructive
  apply paths.
- Optional convenience commands for common repository bootstrap workflows.

## Evaluation Priorities

Before widening the supported surface, `lfguard` should collect feedback on:

- Whether the desired-state shape is expressive enough for platform teams.
- Which Lake Formation resource kinds or grant patterns are missing.
- Which CI outputs are most useful for reviewers.
- How teams want to separate additive changes from destructive maintenance.
- Whether the Python API should expose more structured report helpers.

## Non-Goals

`lfguard` should not become a general AWS provisioning framework. It should not
replace Terraform, CloudFormation, CDK, IAM administration, Lake Formation
administration, or account security controls.

It should continue to keep audit and planning deterministic and AWS-free, with
all live AWS calls isolated in the adapter layer.

## Contributing

Good first contributions are usually small and explicit:

- Add a focused example policy or report fixture.
- Improve an error message without changing behavior.
- Add a test for an existing planner, audit, or adapter path.
- Document an adoption pattern from a real platform workflow.

For code changes, keep the package boundaries in
[`architecture.md`](architecture.md) and the safety rules in
[`safety-model.md`](safety-model.md) intact.
