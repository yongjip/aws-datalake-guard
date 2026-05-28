"""File IO helpers for guardrail state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Type, TypeVar

from .models import CurrentState, DesiredState, GuardrailState


TState = TypeVar("TState", bound=GuardrailState)


class StateFormatError(ValueError):
    """Raised when a desired/current state file cannot be parsed."""


def load_desired(path: str) -> DesiredState:
    return load_state(Path(path), DesiredState)


def load_current(path: str) -> CurrentState:
    return load_state(Path(path), CurrentState)


def load_state(path: Path, state_type: Type[TState]) -> TState:
    raw = _load_mapping(path)
    return state_type.from_dict(raw)


def _load_mapping(path: Path) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StateFormatError("Could not read {}: {}".format(path, exc)) from exc

    suffix = path.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            data = _load_yaml(text, path)
        else:
            data = json.loads(text)
    except ValueError as exc:
        raise StateFormatError("Could not parse {}: {}".format(path, exc)) from exc

    if not isinstance(data, Mapping):
        raise StateFormatError("{} must contain a JSON/YAML object".format(path))
    return data


def _load_yaml(text: str, path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise StateFormatError(
            "{} is YAML, but PyYAML is not installed. Install lfguard[yaml].".format(path)
        ) from exc
    return yaml.safe_load(text)


def dumps_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"
