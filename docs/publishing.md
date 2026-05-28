# Publishing

The package distribution name is `lfguard`; the import package is
`lakeformation_guard`; the primary CLI command is `lfguard`.

## Recommended PyPI Release Path

Use PyPI Trusted Publishing from GitHub Actions rather than storing a long-lived
PyPI token.

Configure a pending publisher in PyPI with:

- PyPI project name: `lfguard`
- Owner: `yongjip`
- Repository: `aws-datalake-guard`
- Workflow: `release.yml`
- Environment: `pypi`

Then publish a GitHub release for a tag such as `v0.1.0`. The release workflow
builds the artifacts, checks them, smoke-tests the built wheel through an
installed `lfguard` CLI, and uploads to PyPI through OIDC.

## Manual Fallback

If Trusted Publishing is not configured yet, build locally and upload with a
project-scoped API token:

```bash
python -m pip install build twine
rm -rf dist build src/*.egg-info
python -m build
python -m twine check dist/*
TWINE_USERNAME=__token__ TWINE_PASSWORD="$PYPI_API_TOKEN" python -m twine upload dist/*
```
