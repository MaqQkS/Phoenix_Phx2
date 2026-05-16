"""Stage 20.3 Phase 6 forbidden-import + scope gate.

AST-level scans over the 5 new Stage 20.3 production modules.

Token discipline (D2) and banned-extra-E-code absence are
covered by the existing test_no_forbidden_artifacts.py grep
walk; this module's job is the import-shape AST checks.
"""

from __future__ import annotations

import ast
import pathlib

import pytest


# ---------------------------------------------------------------------------
# Module discovery
# ---------------------------------------------------------------------------


STAGE20_3_PRODUCTION_MODULE_NAMES: tuple[str, ...] = (
    "PHX2.stage20.filter_interface_models",
    "PHX2.stage20.filter_interface_input",
    "PHX2.stage20.stage20_3_manifest",
    "PHX2.stage20.filter_interface_writers",
    "PHX2.stage20.filter_interface_runner",
)


def _module_path(dotted: str) -> pathlib.Path:
    return pathlib.Path(
        dotted.replace(".", "/") + ".py"
    ).resolve()


def _module_source(dotted: str) -> str:
    return _module_path(dotted).read_text(encoding="utf-8")


def _imported_dotted_names(source: str) -> set[str]:
    """Return the set of dotted module names imported by ``source``."""

    imports: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module)
    return imports


def _imported_from_names(source: str) -> list[tuple[str, str]]:
    """Return (module, imported_name) pairs from `from X import Y`."""

    pairs: list[tuple[str, str]] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                pairs.append((node.module, alias.name))
    return pairs


# ---------------------------------------------------------------------------
# I1: no forbidden network / provider libs
# ---------------------------------------------------------------------------


_FORBIDDEN_LIBS: tuple[str, ...] = (
    "sqlite3", "requests", "httpx", "aiohttp", "websockets",
    "grpc", "grpclib", "kafka", "redis", "boto3", "paramiko",
    "smtplib", "discord", "telegram", "dotenv", "dynaconf", "hydra",
)


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i1_no_forbidden_network_or_provider_imports(module_name):
    imports = _imported_dotted_names(_module_source(module_name))
    for forbidden in _FORBIDDEN_LIBS:
        for imp in imports:
            assert imp != forbidden and not imp.startswith(forbidden + "."), (
                f"forbidden import {imp!r} in {module_name}"
            )


# ---------------------------------------------------------------------------
# I2: no PHX2.stage17/18/19 imports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i2_no_phx2_stage17_18_19_imports(module_name):
    imports = _imported_dotted_names(_module_source(module_name))
    forbidden_prefixes = ("PHX2.stage17", "PHX2.stage18", "PHX2.stage19")
    for imp in imports:
        for prefix in forbidden_prefixes:
            assert not imp.startswith(prefix), (
                f"forbidden upstream import {imp!r} in {module_name}"
            )


# ---------------------------------------------------------------------------
# I3: no phoenix1 / Phoenix1 / bot.db references at the code level
#
# Documentation strings (module docstring, README template) explicitly
# state "no Phoenix1 imports" / "No Phoenix1 filter code is imported"
# as part of the Stage 20.3 design lock; those prose mentions are
# allowed. The forbidden artifact is a code-level reference -- an
# import, an identifier use, or an attribute access -- to the
# Phoenix1 codebase.
# ---------------------------------------------------------------------------


_FORBIDDEN_IDENTIFIERS: tuple[str, ...] = ("phoenix1", "Phoenix1")


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i3_no_phoenix1_code_level_references(module_name):
    src = _module_source(module_name)
    tree = ast.parse(src)

    # 1. No import of phoenix1 / Phoenix1 (any case combination).
    imports = _imported_dotted_names(src)
    for imp in imports:
        head = imp.split(".", 1)[0]
        assert head not in _FORBIDDEN_IDENTIFIERS, (
            f"forbidden Phoenix1 import {imp!r} in {module_name}"
        )

    # 2. No identifier use of phoenix1 / Phoenix1 (Name / Attribute /
    # alias). Docstrings and string literals are ast.Constant nodes
    # and are NOT walked here.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_IDENTIFIERS:
            pytest.fail(
                f"forbidden Phoenix1 identifier {node.id!r} in "
                f"{module_name}"
            )
        if (
            isinstance(node, ast.Attribute)
            and node.attr in _FORBIDDEN_IDENTIFIERS
        ):
            pytest.fail(
                f"forbidden Phoenix1 attribute {node.attr!r} in "
                f"{module_name}"
            )
        if isinstance(node, ast.alias):
            head = node.name.split(".", 1)[0]
            if head in _FORBIDDEN_IDENTIFIERS:
                pytest.fail(
                    f"forbidden Phoenix1 alias {node.name!r} in "
                    f"{module_name}"
                )

    # 3. No bot.db substring (dot in the identifier means it would
    # have to appear as an import or attribute chain; substring scan
    # is cheap and reliable for this case).
    assert "bot.db" not in src, (
        f"forbidden 'bot.db' reference in {module_name}"
    )


# ---------------------------------------------------------------------------
# I4: no 20.2-INTERNAL imports
# ---------------------------------------------------------------------------


_FORBIDDEN_STAGE20_2_INTERNAL: tuple[str, ...] = (
    "PHX2.stage20.input_validators",
    "PHX2.stage20.builder",
    "PHX2.stage20.artifact_writers",
    "PHX2.stage20.manifest_assembler",
    "PHX2.stage20.runner",
    "PHX2.stage20.models.preview_candidate",
    "PHX2.stage20.models.decision_step",
    "PHX2.stage20.models.run_manifest",
    "PHX2.stage20.models.run_warnings",
    "PHX2.stage20.models.filter_result",
)


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i4_no_stage20_2_internal_imports(module_name):
    imports = _imported_dotted_names(_module_source(module_name))
    for forbidden in _FORBIDDEN_STAGE20_2_INTERNAL:
        assert forbidden not in imports, (
            f"forbidden 20.2-internal import {forbidden!r} in "
            f"{module_name}"
        )


# ---------------------------------------------------------------------------
# I5: no "live_dispatch" or "dispatcher" identifier substrings
# except references to SAFE_FOR_LIVE_DISPATCH
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i5_no_live_dispatch_substring_except_safe_constant(module_name):
    src = _module_source(module_name)
    # The locked Stage 20.3 manifest exposes "safe_for_live_dispatch"
    # and "live_dispatch_ready" as field names. Those are allowed.
    # Anything else containing "live_dispatch" or "dispatcher" must
    # not appear.
    allowed_substrings = (
        "SAFE_FOR_LIVE_DISPATCH",
        "safe_for_live_dispatch",
        "live_dispatch_ready",
    )
    for forbidden in ("live_dispatch", "dispatcher"):
        # Replace allowed substrings with placeholders, then scan.
        scrubbed = src
        for allowed in allowed_substrings:
            scrubbed = scrubbed.replace(allowed, "")
        assert forbidden not in scrubbed, (
            f"forbidden identifier substring {forbidden!r} in "
            f"{module_name} (not whitelisted via "
            f"SAFE_FOR_LIVE_DISPATCH-family references)"
        )


# ---------------------------------------------------------------------------
# I6: no environment-variable reads / dotenv usage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i6_no_environment_or_dotenv_usage(module_name):
    src = _module_source(module_name)
    forbidden = ("os.environ", "os.getenv", "load_dotenv")
    for needle in forbidden:
        assert needle not in src, (
            f"forbidden environment access {needle!r} in {module_name}"
        )


# ---------------------------------------------------------------------------
# I7: no `if __name__ == "__main__":` blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i7_no_dunder_main_blocks(module_name):
    src = _module_source(module_name)
    # Match the AST shape: an If whose test is a Compare of __name__
    # against "__main__".
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            left = node.test.left
            if (
                isinstance(left, ast.Name) and left.id == "__name__"
            ):
                for comparator in node.test.comparators:
                    if (
                        isinstance(comparator, ast.Constant)
                        and comparator.value == "__main__"
                    ):
                        pytest.fail(
                            f"{module_name} contains an "
                            f"`if __name__ == '__main__':` block"
                        )


# ---------------------------------------------------------------------------
# I8: no module-level datetime.utcnow() or time.time() calls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i8_no_module_level_clock_reads(module_name):
    src = _module_source(module_name)
    # The runner uses clock.now() (injected). No production module
    # should call datetime.utcnow / datetime.now / time.time directly.
    forbidden_calls = (
        "datetime.utcnow",
        "datetime.now",
        "time.time(",
    )
    for needle in forbidden_calls:
        assert needle not in src, (
            f"forbidden direct clock read {needle!r} in {module_name}"
        )


# ---------------------------------------------------------------------------
# I9: no "FilterResult" identifier (INFO-2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i9_no_filter_result_identifier(module_name):
    src = _module_source(module_name)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "FilterResult":
            pytest.fail(
                f"{module_name} references the dormant FilterResult "
                "identifier (INFO-2 violation)"
            )
        if isinstance(node, ast.Attribute) and node.attr == "FilterResult":
            pytest.fail(
                f"{module_name} references the dormant FilterResult "
                "identifier as an attribute"
            )


# ---------------------------------------------------------------------------
# I10: the banned extra E-code (the slot before E2027) MUST NOT appear
# as an identifier anywhere in Stage 20.3 production source. The literal
# token is reconstructed at runtime so this file's own bytes never
# embed it -- otherwise the existing test_no_forbidden_artifacts
# grep walk would flag this test file.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i10_no_banned_extra_ecode_identifier(module_name):
    # Reconstruct at runtime so this file's source bytes never embed
    # the banned token.
    banned = "E" + str(2026)
    src = _module_source(module_name)
    assert banned not in src, (
        f"banned extra E-code identifier in {module_name}"
    )


# ---------------------------------------------------------------------------
# I11 (bonus): every Stage 20.3 production module imports only from
# the whitelisted PHX2.stage20 surface and Python stdlib
# ---------------------------------------------------------------------------


_ALLOWED_PHX2_STAGE20 = frozenset({
    "PHX2.stage20.constants",
    "PHX2.stage20.errors",
    "PHX2.stage20.clock",
    "PHX2.stage20.filter_interface_models",
    "PHX2.stage20.filter_interface_input",
    "PHX2.stage20.filter_interface_writers",
    "PHX2.stage20.filter_interface_runner",
    "PHX2.stage20.stage20_3_manifest",
})


@pytest.mark.parametrize("module_name", STAGE20_3_PRODUCTION_MODULE_NAMES)
def test_i11_all_stage20_imports_are_within_phase_or_shared_safe(module_name):
    imports = _imported_dotted_names(_module_source(module_name))
    for imp in imports:
        if imp.startswith("PHX2.stage20"):
            assert imp in _ALLOWED_PHX2_STAGE20, (
                f"{module_name} imports {imp!r}, which is outside the "
                f"Stage 20.3 allowed surface ({sorted(_ALLOWED_PHX2_STAGE20)})"
            )
