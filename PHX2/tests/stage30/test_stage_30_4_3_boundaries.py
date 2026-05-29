"""Stage 30.4.3 Birdeye source bridge boundary tests.

Scans the single Stage 30.4.3 production .py file
(``stage30_4_3_market_context_birdeye_source.py``) for:

  * forbidden runtime imports (``os`` / ``dotenv`` / ``keyring`` /
    ``requests`` / ``httpx`` / ``aiohttp`` / ``urllib`` / ``socket`` /
    ``grpc`` / ``asyncio`` / ``websocket`` / ``websockets`` /
    ``http`` / ``ssl``),
  * forbidden text needles (URL hosts, inbound-hook hosts, bearer
    tokens, API keys, RPC provider names),
  * forbidden transport-construction needles,
  * forbidden Stage 21-28 production imports + PHX1,
  * Stage 29 imports limited to the four approved Stage 29.2 modules,
  * all PHX2 imports being a subset of the documented Stage 30.4.3
    bridge allowlist (the four Stage 29.2 modules + the two Stage
    30.4.1 offline siblings),
  * no Discord / provider import surface,
  * no ``os.environ`` / ``os.getenv`` / ``os.environb`` access,
  * zero top-level Call nodes (no implicit I/O at import time),
  * the produced reading echoing NO raw response body, URL, endpoint
    credential, request header, or endpoint secret.

Fake transport only. No live call.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping, Set, Tuple

from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
    Stage30_4_3BirdeyeMarketContextSource,
)
from PHX2.stage30.stage30_4_manifest import (
    STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS,
    STAGE30_4_3_MARKET_CONTEXT_BIRDEYE_SOURCE_BASENAME,
    STAGE30_4_3_STAGE29_2_REUSE_ALLOWLIST,
    STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_3,
    STAGE30_4_FORBIDDEN_TEXT_NEEDLES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"

BRIDGE_PATH: Path = (
    STAGE30_ROOT / STAGE30_4_3_MARKET_CONTEXT_BIRDEYE_SOURCE_BASENAME
)


_VALID_MINT: str = "So11111111111111111111111111111111111111112"
_OBSERVED_TS: str = "2026-05-28T11:59:30Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bridge_source() -> str:
    return BRIDGE_PATH.read_text(encoding="utf-8")


def _bridge_ast() -> ast.Module:
    return ast.parse(_bridge_source())


def _bridge_imports() -> Set[str]:
    tree = _bridge_ast()
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


# ---------------------------------------------------------------------------
# 1. File exists + manifest pin
# ---------------------------------------------------------------------------


def test_bridge_file_exists() -> None:
    assert BRIDGE_PATH.is_file(), (
        f"Stage 30.4.3 requires the bridge at {BRIDGE_PATH}"
    )


def test_manifest_pins_bridge_basename() -> None:
    assert STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_3 == (
        "stage30_4_3_market_context_birdeye_source.py",
    )


# ---------------------------------------------------------------------------
# 2. Module imports cleanly (smoke)
# ---------------------------------------------------------------------------


def test_bridge_module_imports_cleanly() -> None:
    import PHX2.stage30.stage30_4_3_market_context_birdeye_source  # noqa: E501,F401


# ---------------------------------------------------------------------------
# 3. No env import / env attribute access
# ---------------------------------------------------------------------------


def test_bridge_does_not_import_os() -> None:
    imports = _bridge_imports()
    assert "os" not in imports
    for target in imports:
        assert not target.startswith("os."), (
            f"bridge must not import os.*; offender: {target!r}"
        )


def test_bridge_does_not_import_dotenv_or_keyring() -> None:
    imports = _bridge_imports()
    for forbidden in ("dotenv", "keyring"):
        assert forbidden not in imports
        for target in imports:
            assert not target.startswith(forbidden + ".")


def test_bridge_does_not_access_environ() -> None:
    tree = _bridge_ast()
    os_aliases: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    assert alias.name not in {
                        "environ",
                        "getenv",
                        "environb",
                    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in {"environ", "getenv", "environb"}
            ):
                raise AssertionError(
                    "bridge must not perform os.environ / os.getenv "
                    "/ os.environb attribute access"
                )


# ---------------------------------------------------------------------------
# 4. No network module imports
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK_MODULES: Tuple[str, ...] = (
    "urllib",
    "urllib.request",
    "urllib.parse",
    "urllib.error",
    "socket",
    "grpc",
    "asyncio",
    "aiohttp",
    "httpx",
    "requests",
    "websockets",
    "websocket",
    "http",
    "http.client",
    "ssl",
)


def test_bridge_does_not_import_network_modules() -> None:
    imports = _bridge_imports()
    for target in imports:
        for forbidden in _FORBIDDEN_NETWORK_MODULES:
            assert not (
                target == forbidden
                or target.startswith(forbidden + ".")
            ), (
                f"bridge must not import network module "
                f"{forbidden!r}; offender: {target!r}"
            )


# ---------------------------------------------------------------------------
# 5. No Stage 21-28 imports; no PHX1; Stage 29 limited to the four
# ---------------------------------------------------------------------------


def test_bridge_does_not_import_stage_21_28_or_phx1() -> None:
    imports = _bridge_imports()
    for target in imports:
        for stage_n in range(21, 29):
            forbidden_prefix = f"PHX2.stage{stage_n}"
            assert not (
                target == forbidden_prefix
                or target.startswith(forbidden_prefix + ".")
            ), (
                f"bridge must not import Stage 21-28 module "
                f"{target!r}"
            )
        assert not target.startswith("PHX1"), (
            f"bridge must not import PHX1 module {target!r}"
        )


def test_bridge_stage29_imports_limited_to_approved_four() -> None:
    imports = _bridge_imports()
    for target in imports:
        if target.startswith("PHX2.stage29"):
            assert target in STAGE30_4_3_STAGE29_2_REUSE_ALLOWLIST, (
                f"bridge Stage 29 import {target!r} is not one of the "
                f"four approved Stage 29.2 modules "
                f"{sorted(STAGE30_4_3_STAGE29_2_REUSE_ALLOWLIST)!r}"
            )


# ---------------------------------------------------------------------------
# 6. All PHX2 imports subset of the documented bridge allowlist
# ---------------------------------------------------------------------------


def test_bridge_phx2_imports_subset_of_allowlist() -> None:
    imports = _bridge_imports()
    for target in imports:
        if not target.startswith("PHX2."):
            continue
        assert target in STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS, (
            f"bridge PHX2 import {target!r} is not in the documented "
            f"allowlist {sorted(STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS)!r}"
        )


# ---------------------------------------------------------------------------
# 7. No Discord / provider import surface (non-PHX2 targets)
# ---------------------------------------------------------------------------


_FORBIDDEN_PROVIDER_NEEDLES: Tuple[str, ...] = (
    "discord",
    "telegram",
    "birdeye",
    "hel" + "ius",
    "chain" + "stack",
    "pump",
    "solders",
    "solana",
    "web" + "hook",
    "dex" + "screener",
)


def test_bridge_does_not_import_provider_or_discord_modules() -> None:
    imports = _bridge_imports()
    for target in imports:
        # PHX2.stage29.* module paths legitimately carry "birdeye";
        # the subset check above already pins them. Only scan non-PHX2
        # import targets here.
        if target.startswith("PHX2."):
            continue
        lower = target.lower()
        for needle in _FORBIDDEN_PROVIDER_NEEDLES:
            assert needle not in lower, (
                f"bridge must not import provider / Discord surface "
                f"{needle!r}; offender: {target!r}"
            )


# ---------------------------------------------------------------------------
# 8. No forbidden text needles
# ---------------------------------------------------------------------------


def test_bridge_text_carries_no_forbidden_needles() -> None:
    text = _bridge_source().lower()
    for needle in STAGE30_4_FORBIDDEN_TEXT_NEEDLES:
        needle_lower = needle.lower()
        assert needle_lower not in text, (
            f"bridge carries forbidden text needle {needle!r}"
        )


def test_bridge_text_carries_no_transport_construction_needles() -> None:
    needles = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "ses" + "sion.post",
        "ses" + "sion.get",
        "requests." + "post",
        "requests." + "get",
        "client." + "post",
        "client." + "get",
        "url" + "open",
    )
    text = _bridge_source().lower()
    for needle in needles:
        assert needle.lower() not in text, (
            f"bridge carries transport-construction needle {needle!r}"
        )


# ---------------------------------------------------------------------------
# 9. Zero top-level Call nodes (no implicit I/O at import time)
# ---------------------------------------------------------------------------


def test_bridge_has_no_top_level_call_nodes() -> None:
    tree = _bridge_ast()
    hits = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(
            stmt.value, ast.Call
        ):
            hits.append(ast.dump(stmt.value))
        if isinstance(stmt, ast.Assign) and isinstance(
            stmt.value, ast.Call
        ):
            hits.append(ast.dump(stmt.value))
        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None and isinstance(
                stmt.value, ast.Call
            ):
                hits.append(ast.dump(stmt.value))
    assert not hits, (
        f"bridge must carry zero top-level Call nodes; offenders: "
        f"{hits!r}"
    )


# ---------------------------------------------------------------------------
# 10. Reading echoes no raw body / URL / credential / header / secret
# ---------------------------------------------------------------------------


class _FakeTransport:
    def __init__(self, result: Stage29_2BirdeyeHttpResult) -> None:
        self._result = result
        self.calls: list = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append(
            (path, dict(query_params), timeout_seconds)
        )
        return self._result


def test_reading_does_not_echo_raw_body_url_credential_or_secret() -> None:
    # Sentinel values that must NEVER appear on the produced reading.
    sentinel_secret = "SENTINELKEYVALUEAAAA"  # 20 chars, safe shape
    sentinel_base = "https://sentinel.endpoint.fake"
    sentinel_url_in_body = "https://leak.endpoint.fake/raw"
    sentinel_blob = "LEAKEDRAWRESPONSEBLOB"

    endpoint_secret = Stage29_2BirdeyeEndpointSecret(
        _api_key=sentinel_secret,
        _base_url=sentinel_base,
    )
    # The canned body carries extra junk fields (a URL, a raw blob)
    # the bridge must ignore. It reads only data.mc / data.liquidity.
    result = Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body={
            "data": {"mc": 83000, "liquidity": 27000},
            "url": sentinel_url_in_body,
            "raw_response": sentinel_blob,
        },
        fetched_at_utc=_OBSERVED_TS,
    )
    source = Stage30_4_3BirdeyeMarketContextSource(
        transport=_FakeTransport(result),
        endpoint_secret=endpoint_secret,
        timeout_seconds=30,
    )
    reading = source.read(_VALID_MINT)
    assert reading is not None

    forbidden = (
        sentinel_secret,
        sentinel_base,
        "sentinel.endpoint.fake",
        sentinel_url_in_body,
        sentinel_blob,
    )
    rep = repr(reading)
    for token in forbidden:
        assert token not in rep, (
            f"reading repr leaked {token!r}"
        )
        for field_value in reading:
            if isinstance(field_value, str):
                assert token not in field_value, (
                    f"reading field leaked {token!r}"
                )

    # The reading carries only the canonical mapped values + envelope.
    assert reading.market_cap_usd_value == "83000"
    assert reading.liquidity_usd_value == "27000"
    assert reading.source_label == "birdeye_token_overview"
