"""Small, secret-safe dotenv projection shared by provider tooling.

This module deliberately does not mutate ``os.environ``.  It reads only a
caller's allow-listed names, gives an explicitly supplied process environment
precedence over the file (including an explicitly empty value), and keeps raw
values behind redacted wrappers.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
import os
from pathlib import Path
from typing import Optional


class _SecretText:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = str(value)

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "<REDACTED>"

    def __str__(self) -> str:
        return "<REDACTED>"


class SecretEnvironment(Mapping[str, str]):
    """Read-only mapping whose representation contains presence only."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = {
            str(name): _SecretText(str(value))
            for name, value in values.items()
        }

    def __getitem__(self, name: str) -> str:
        return self._values[name].reveal()

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        names = ",".join(sorted(self._values))
        return f"SecretEnvironment(present=[{names}])"

    def select(self, names: Sequence[str]) -> "SecretEnvironment":
        allowed = frozenset(str(name) for name in names)
        return SecretEnvironment(
            {
                name: value.reveal()
                for name, value in self._values.items()
                if name in allowed
            }
        )

    def sanitized_presence(
        self, names: Optional[Sequence[str]] = None
    ) -> dict[str, str]:
        selected = tuple(self._values) if names is None else tuple(names)
        return {
            name: (
                "PRESENT"
                if name in self._values
                and bool(self._values[name].reveal().strip())
                else "MISSING"
            )
            for name in selected
        }


def _parse_allowlisted_dotenv(
    path: Optional[Path], *, names: Sequence[str]
) -> dict[str, str]:
    values: dict[str, str] = {}
    allowed = frozenset(str(name) for name in names)
    if path is None or not path.is_file():
        return values
    for original in path.read_text(encoding="utf-8").splitlines():
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, raw = line.split("=", 1)
        name = name.strip()
        if name not in allowed:
            continue
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        values[name] = raw
    return values


def load_secret_environment(
    *,
    env_path: Optional[Path],
    names: Sequence[str],
    environ: Optional[Mapping[str, str]] = None,
) -> SecretEnvironment:
    """Load an allow-listed dotenv projection without changing the process."""

    canonical_names = tuple(dict.fromkeys(str(name) for name in names))
    values = _parse_allowlisted_dotenv(env_path, names=canonical_names)
    source = os.environ if environ is None else environ
    for name in canonical_names:
        if name not in source:
            continue
        candidate = source.get(name)
        if isinstance(candidate, str):
            values[name] = candidate.strip()
    return SecretEnvironment(values)


__all__ = ("SecretEnvironment", "load_secret_environment")
