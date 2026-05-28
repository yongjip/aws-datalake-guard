# Contributing

Thanks for improving `lfguard`.

## Development Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev,aws,yaml]"
python -m unittest discover -s tests
```

## Design Constraints

- Keep audit and plan logic deterministic and AWS-free.
- Keep boto3 calls in the adapter layer.
- Default plans must remain conservative: no revokes or removals unless the user explicitly enables them.
- Add tests for every planner, audit, or apply behavior change.
- Prefer JSON-compatible public payloads so CLI output can be consumed by CI systems.

## Release Checks

```bash
python -m unittest discover -s tests
python -m build
python -m twine check dist/*
```
