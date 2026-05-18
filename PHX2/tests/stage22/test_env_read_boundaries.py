"""Stage 22 env-read boundary tests.

The contract: NO Stage 22 module reads the process environment.

Stage 22.1 has NO ``config.py`` -- the future Stage 22 runner
will receive a typed config snapshot from a separately-defined
seam (likely a thin wrapper around the Stage 21 env-read
boundary; that seam is Stage 22.2+ scope). Stage 22.1
production code MUST NOT read ``os.environ`` / ``os.getenv``
under any form.

The AST-level detector tracks aliasing so the following forms
are all caught:

  * ``os.environ`` / ``os.getenv``
  * ``import os as _os; _os.environ`` (any os alias)
  * ``from os import environ`` / ``from os import getenv``
  * ``from os import environ as e`` / ``from os import getenv as g``
  * ``from os.environ import ...``
  * ``getattr(os, "environ")`` / ``getattr(os, "getenv")``
  * ``getattr(_os, "environ")`` (any os alias)
  * ``os.environb`` (bytes view) -- defense-in-depth
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE22_ROOT = Path(__file__).parent.parent.parent / "stage22"


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE22_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _module_reads_env_in_source(source: str) -> bool:
    """Return True iff the parsed source contains an env-read edge.

    Tracks ``os`` aliases, ``environ`` / ``getenv`` import
    aliases, and ``getattr`` indirection. Comment / docstring
    mentions are not detected because they never produce a
    relevant AST node.
    """
    tree = ast.parse(source)

    os_aliases: set[str] = set()
    env_call_aliases: set[str] = set()
    env_attr_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "os":
                for alias in node.names:
                    bound_name = alias.asname or alias.name
                    if alias.name in ("environ", "environb"):
                        env_attr_aliases.add(bound_name)
                    elif alias.name == "getenv":
                        env_call_aliases.add(bound_name)
            elif mod == "os.environ" or mod.startswith("os.environ."):
                return True

    if env_attr_aliases or env_call_aliases:
        return True

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _ENV_ATTR_NAMES
            ):
                return True
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in os_aliases
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value in _ENV_ATTR_NAMES
            ):
                return True

    return False


def _module_reads_env_in_file(file_path: Path) -> bool:
    return _module_reads_env_in_source(
        file_path.read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Production-tree checks
# ---------------------------------------------------------------------------


def test_no_stage22_module_reads_environ():
    for py_file in _iter_production_modules():
        assert not _module_reads_env_in_file(py_file), (
            f"{py_file}: forbidden env-read pattern. Stage 22 "
            "contract: no Stage 22 module may read the process "
            "environment in 22.1."
        )


def test_stage22_has_no_env_reading_module():
    reading_modules = [
        p for p in _iter_production_modules()
        if _module_reads_env_in_file(p)
    ]
    assert reading_modules == [], (
        f"Stage 22.1 must have zero env-reading modules; got "
        f"{reading_modules}"
    )


# ---------------------------------------------------------------------------
# Negative fixtures: prove the detector flags every problem shape
# ---------------------------------------------------------------------------


def test_detector_catches_plain_os_environ():
    source = "import os\nx = os.environ['KEY']\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_plain_os_getenv():
    source = "import os\nx = os.getenv('KEY')\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_aliased_os_environ():
    source = "import os as _os\nx = _os.environ['KEY']\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_aliased_os_getenv():
    source = "import os as _os\nx = _os.getenv('KEY')\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_from_os_import_environ():
    source = "from os import environ\nx = environ['KEY']\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_from_os_import_getenv():
    source = "from os import getenv\nx = getenv('KEY')\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_from_os_import_environ_aliased():
    source = "from os import environ as _e\nx = _e['KEY']\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_from_os_import_getenv_aliased():
    source = "from os import getenv as _g\nx = _g('KEY')\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_from_os_environ_import_x():
    source = "from os.environ import something\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_getattr_os_environ():
    source = "import os\nx = getattr(os, 'environ')\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_getattr_os_getenv():
    source = "import os\nx = getattr(os, 'getenv')\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_getattr_aliased_os_environ():
    source = "import os as _os\nx = getattr(_os, 'environ')\n"
    assert _module_reads_env_in_source(source)


def test_detector_catches_aliased_os_environb():
    source = "import os as _os\nx = _os.environb[b'KEY']\n"
    assert _module_reads_env_in_source(source)


def test_detector_ignores_docstring_mention():
    source = '"""docstring talks about os.environ but does not read it."""\n'
    assert not _module_reads_env_in_source(source)


def test_detector_ignores_string_literal_mention():
    source = "msg = 'os.environ is forbidden in Stage 22.1'\n"
    assert not _module_reads_env_in_source(source)


def test_detector_ignores_unrelated_getattr_calls():
    source = (
        "class Fake:\n"
        "    environ = {}\n"
        "f = Fake()\n"
        "x = getattr(f, 'environ')\n"
    )
    assert not _module_reads_env_in_source(source)
