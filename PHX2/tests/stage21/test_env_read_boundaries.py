"""Stage 21 env-read boundary tests.

The contract: only ``PHX2/stage21/config.py`` may import / read
``os.environ`` or ``os.getenv``. Every other Stage 21 module
receives typed config / secret / attestation objects.

The check is AST-level on Stage 21 production modules. It detects:
  * ``import os`` followed by ``os.environ`` / ``os.getenv`` access
    anywhere in the module body;
  * ``from os import environ`` / ``from os import getenv``;
  * ``from os.environ import ...``.

The ``os`` module itself MAY be imported by other Stage 21 modules
for non-env-reading purposes (e.g. ``os.sep``) -- the check looks
for the specific names ``environ`` / ``getenv`` rather than a
broad ``os`` import ban.
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE21_ROOT = Path(__file__).parent.parent.parent / "stage21"
CONFIG_PATH = STAGE21_ROOT / "config.py"


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE21_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _module_reads_os_env(file_path: Path) -> bool:
    """Return True if the module references ``os.environ`` / ``os.getenv``.

    Detects:
      * ``Attribute(value=Name('os'), attr='environ' | 'getenv')``
      * ``ImportFrom(module='os', names=[Alias('environ' | 'getenv')])``
      * ``ImportFrom(module='os.environ', ...)``
    """
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr in ("environ", "getenv")
            ):
                return True
        if isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    if alias.name in ("environ", "getenv"):
                        return True
            if node.module and node.module.startswith("os.environ"):
                return True
    return False


def test_config_module_is_allowed_to_read_environ():
    assert _module_reads_os_env(CONFIG_PATH), (
        "PHX2/stage21/config.py should be the single Stage 21 env-read "
        "boundary; this test fails if config.py no longer reads "
        "os.environ / os.getenv."
    )


def test_no_other_stage21_module_reads_environ():
    for py_file in _iter_production_modules():
        if py_file == CONFIG_PATH:
            continue
        assert not _module_reads_os_env(py_file), (
            f"{py_file}: forbidden os.environ / os.getenv reference. "
            f"Stage 21 contract: only PHX2/stage21/config.py may read "
            f"the process environment."
        )


def test_config_is_the_only_module_with_an_os_environ_attribute_access():
    """Belt-and-suspenders: assert exactly one module reads the env."""
    reading_modules = [
        p for p in _iter_production_modules()
        if _module_reads_os_env(p)
    ]
    assert reading_modules == [CONFIG_PATH], (
        f"expected exactly one env-reading module (config.py); "
        f"got {reading_modules}"
    )
