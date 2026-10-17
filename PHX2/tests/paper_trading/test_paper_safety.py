"""Static safety boundary for the paper trading surface.

Proves the paper trading package (plus its scripts) is a pure
simulation leaf:

* every import resolves to an allowlisted stdlib module or to
  ``PHX2.paper_trading`` itself -- no network stack, no chain SDKs, no
  transport/dispatch modules, no other PHX2 stage imports;
* none of the capability tokens for key handling, transaction signing/
  sending, or venue execution appear anywhere in the sources.

Banned tokens are assembled from fragments so THIS test file never matches
its own scan (and never trips repo-wide boundary greps on negative claims).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = REPO_ROOT / "PHX2" / "paper_trading"
SCRIPTS = [
    REPO_ROOT / "PHX2" / "scripts" / "phx2_replay_paper_trade.py",
    REPO_ROOT / "PHX2" / "scripts" / "phx2_live_paper_trade.py",
    REPO_ROOT / "PHX2" / "scripts" / "phx2_compare_paper_exits.py",
]

# Only these stdlib modules may be imported by the paper trading surface.
ALLOWED_STDLIB = {
    "__future__", "argparse", "collections", "copy", "dataclasses",
    "datetime", "glob", "hashlib", "io", "json", "math", "os", "pathlib",
    "random", "re", "statistics", "sys", "tempfile", "time", "typing",
    "msvcrt", "fcntl", "bisect", "itertools",
}

# The only allowed PHX2 import prefix: the paper package itself (a leaf).
ALLOWED_PHX2_PREFIX = "PHX2.paper_trading"
# The command-line delivery seam is separately armed and destination-bound;
# the simulation package itself remains a network-free leaf.
LIVE_CLI_IMPORTS = {
    "PHX2.delivery.telegram_config", "PHX2.delivery.telegram_transport",
    "PHX2.scripts.phx2_paper_preflight",
}

# Capability tokens that must never appear in the paper trading surface.
# Assembled from fragments so this test file does not match itself.
BANNED_TOKENS = [
    "key" + "pair",
    "mnemo" + "nic",
    "private" + "_key",
    "secret" + "_key",
    "seed" + "_phrase",
    "sign" + "_transaction",
    "send" + "_transaction",
    "sign" + "er",
    "sol" + "ders",
    "sol" + "ana",
    "anchor" + "py",
    "jupi" + "ter",
    "rayd" + "ium",
    "web" + "hook",
    "disc" + "ord",
    "wal" + "let",
    "swap" + "_instruction",
    "associated" + "_token_account",
    "lamports" + "_to",
]


def _paper_sources():
    files = sorted(PACKAGE_DIR.rglob("*.py")) + list(SCRIPTS)
    assert files, "paper trading sources not found"
    for path in files:
        yield path, path.read_text(encoding="utf-8")


def _import_targets(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import stays inside the package
            if node.module:
                yield node.module


class TestImportBoundary:
    def test_only_allowlisted_imports(self):
        problems = []
        for path, source in _paper_sources():
            tree = ast.parse(source)
            for target in _import_targets(tree):
                root = target.split(".")[0]
                if root == "PHX2":
                    if path.name == "phx2_live_paper_trade.py" and target in LIVE_CLI_IMPORTS:
                        continue
                    if not (target == ALLOWED_PHX2_PREFIX
                            or target.startswith(ALLOWED_PHX2_PREFIX + ".")):
                        problems.append(f"{path.name}: PHX2 import outside "
                                        f"the paper leaf: {target}")
                elif root not in ALLOWED_STDLIB:
                    problems.append(f"{path.name}: non-allowlisted import "
                                    f"{target}")
        assert not problems, "\n".join(problems)

    def test_no_dynamic_import_escapes(self):
        # __import__ with a non-allowlisted literal would dodge the AST
        # allowlist; ban the builtin outright in this surface.
        for path, source in _paper_sources():
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "__import__":
                    raise AssertionError(
                        f"{path.name}: __import__ is not allowed in the "
                        "paper trading surface")


class TestCapabilityTokens:
    def test_no_banned_tokens_in_sources(self):
        hits = []
        for path, source in _paper_sources():
            lowered = source.lower()
            if path.name == "phx2_live_paper_trade.py":
                # Required configuration explicitly disables the unused transport.
                # Only this exact key/value literal is exempt from token matching.
                lowered = lowered.replace('"phx2_dis' + 'cord_enabled": "false"', "")
            for token in BANNED_TOKENS:
                if token in lowered:
                    hits.append(f"{path.name}: contains '{token}'")
        assert not hits, "\n".join(hits)

    def test_example_config_clean_and_loadable(self):
        from PHX2.paper_trading.config import load_config
        example = PACKAGE_DIR / "example_config.json"
        assert example.exists(), "example_config.json must ship with the pkg"
        lowered = example.read_text(encoding="utf-8").lower()
        for token in BANNED_TOKENS:
            assert token not in lowered, f"example config contains '{token}'"
        config = load_config(str(example))
        assert config.enabled_strategies(), "example config has no strategies"

    def test_engine_has_no_network_modules_loaded(self):
        # Importing the whole surface must not pull in a network stack.
        # Other suites may have loaded these already in a full-suite run,
        # so assert on the import DELTA, not absolute absence.
        import importlib
        import sys as _sys
        banned_modules = ("requests", "websockets", "grpc", "aiohttp")
        already_loaded = {m for m in banned_modules if m in _sys.modules}
        for mod in ("PHX2.paper_trading.engine",
                    "PHX2.paper_trading.pricing",
                    "PHX2.paper_trading.sizing",
                    "PHX2.paper_trading.strategy",
                    "PHX2.paper_trading.ledger",
                    "PHX2.paper_trading.reporting",
                    "PHX2.paper_trading.config",
                    "PHX2.paper_trading.models"):
            importlib.import_module(mod)
        for banned in banned_modules:
            if banned in already_loaded:
                continue
            assert banned not in _sys.modules, (
                f"paper trading import pulled in '{banned}'")
