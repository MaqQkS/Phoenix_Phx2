"""Stage 21 env-read boundary tests.

The contract: only ``PHX2/stage21/config.py`` may read the
process environment. Every other Stage 21 module receives typed
config / secret / attestation objects produced by the config
module.

AUDIT-002: the AST-level detector tracks aliasing so the
following forms are all caught:

  * ``os.environ`` / ``os.getenv``
  * ``import os as _os; _os.environ`` (any os alias)
  * ``from os import environ`` / ``from os import getenv``
  * ``from os import environ as e`` / ``from os import getenv as g``
  * ``from os.environ import ...``
  * ``getattr(os, "environ")`` / ``getattr(os, "getenv")``
  * ``getattr(_os, "environ")`` (any os alias)
  * ``os.environb`` (bytes view) -- defense-in-depth

Docstring and comment mentions are ignored: the detector
operates on the AST, not on raw text.
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE21_ROOT = Path(__file__).parent.parent.parent / "stage21"
CONFIG_PATH = STAGE21_ROOT / "config.py"


_ENV_ATTR_NAMES: frozenset[str] = frozenset({"environ", "getenv", "environb"})


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE21_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _module_reads_env_in_source(source: str) -> bool:
    """Return True iff the parsed source contains an env-read edge.

    Tracks os aliases, environ/getenv import aliases, and getattr
    indirection. Comment / docstring mentions are not detected
    because they never produce a relevant AST node.
    """
    tree = ast.parse(source)

    # Pass 1: collect aliases.
    os_aliases: set[str] = set()
    env_call_aliases: set[str] = set()  # names bound to os.getenv
    env_attr_aliases: set[str] = set()  # names bound to os.environ / os.environb

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # ``import os`` / ``import os as _os``
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
                # ``from os.environ import X`` -- the import itself
                # is an env-read edge.
                return True

    # Imports of env names are themselves treated as the env-read
    # edge (matches the Stage 20 convention: if you imported
    # ``environ`` you are presumed to use it).
    if env_attr_aliases or env_call_aliases:
        return True

    # Pass 2: walk for access patterns through os aliases.
    for node in ast.walk(tree):
        # os_alias.environ / os_alias.getenv / os_alias.environb
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _ENV_ATTR_NAMES
            ):
                return True
        # getattr(os_alias, "environ"|"getenv"|"environb")
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


def test_config_module_is_allowed_to_read_environ():
    assert _module_reads_env_in_file(CONFIG_PATH), (
        "PHX2/stage21/config.py should be the single Stage 21 env-read "
        "boundary; this test fails if config.py no longer reads "
        "os.environ / os.getenv."
    )


def test_no_other_stage21_module_reads_environ():
    for py_file in _iter_production_modules():
        if py_file == CONFIG_PATH:
            continue
        assert not _module_reads_env_in_file(py_file), (
            f"{py_file}: forbidden env-read pattern. Stage 21 "
            f"contract: only PHX2/stage21/config.py may read the "
            f"process environment."
        )


def test_config_is_the_only_env_reading_module():
    reading_modules = [
        p for p in _iter_production_modules()
        if _module_reads_env_in_file(p)
    ]
    assert reading_modules == [CONFIG_PATH], (
        f"expected exactly one env-reading module (config.py); "
        f"got {reading_modules}"
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


def test_detector_ignores_plain_import_os_with_no_env_access():
    # Importing the ``os`` module alone is not a violation; only
    # actual env-name access counts.
    source = "import os\nprint(os.sep)\n"
    assert not _module_reads_env_in_source(source)


def test_detector_ignores_docstring_mention():
    source = '"""docstring talks about os.environ but does not read it."""\n'
    assert not _module_reads_env_in_source(source)


def test_detector_ignores_string_literal_mention():
    source = "msg = 'os.environ is forbidden outside config.py'\n"
    assert not _module_reads_env_in_source(source)


def test_detector_ignores_unrelated_getattr_calls():
    # getattr(other_module, "environ") is not flagged because the
    # first arg is not in the os_aliases set.
    source = (
        "class Fake:\n"
        "    environ = {}\n"
        "f = Fake()\n"
        "x = getattr(f, 'environ')\n"
    )
    assert not _module_reads_env_in_source(source)
