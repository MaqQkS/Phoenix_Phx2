"""Stage 29.2 birdeye_constants.py pin tests.

Locks the Stage 29.2 program-pinned constants, schema version
strings, OHLCV closed-set allow-list, safe-shape validators, and
the absence of any URL host literal / raw API-key-looking
substring.
"""

from __future__ import annotations

import pytest

from PHX2.stage29 import birdeye_constants as C


# ---------------------------------------------------------------------------
# Version + schema pins
# ---------------------------------------------------------------------------


def test_minor_version_is_29_2():
    assert C.STAGE29_2_MINOR_VERSION == "29.2"


def test_snapshot_schema_version_pinned():
    assert (
        C.STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION
        == "stage29_2_birdeye_snapshot_v0"
    )


def test_evidence_schema_version_pinned():
    assert (
        C.STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION
        == "stage29_2_birdeye_evidence_v0"
    )


def test_probe_schema_version_pinned():
    assert (
        C.STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION
        == "stage29_2_birdeye_probe_v0"
    )


def test_readiness_schema_version_pinned():
    assert (
        C.STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION
        == "stage29_2_birdeye_readiness_v0"
    )


def test_redaction_token_pinned():
    assert C.STAGE29_2_REDACTION_TOKEN == "<<STAGE29_2_REDACTED>>"


def test_redaction_token_is_distinct_from_other_stages():
    # The Stage 29.2 redaction token must NOT collide with any
    # Stage 27 / 28.x / 29.1 token so a leak-scan test for one
    # cannot collide with another.
    assert "STAGE29_2" in C.STAGE29_2_REDACTION_TOKEN
    assert "STAGE28" not in C.STAGE29_2_REDACTION_TOKEN
    assert "STAGE29_1" not in C.STAGE29_2_REDACTION_TOKEN


# ---------------------------------------------------------------------------
# Endpoint path pins
# ---------------------------------------------------------------------------


def test_endpoint_path_price_pinned():
    assert C.BIRDEYE_PATH_PRICE == "/defi/price"


def test_endpoint_path_ohlcv_pinned():
    assert C.BIRDEYE_PATH_OHLCV == "/defi/ohlcv"


def test_endpoint_path_token_overview_pinned():
    # Stage 30.4.3 authorized the token-overview path so the Stage
    # 30.4 compact market-context bridge can read current MC + LP.
    assert C.BIRDEYE_PATH_TOKEN_OVERVIEW == "/defi/token_overview"


def test_endpoint_path_history_price_NOT_present():
    # Stage 29.2 explicitly does NOT use /defi/history_price for
    # ATH; the endpoint shape (close-only `value` per bucket)
    # systematically under-reports ATH vs /defi/ohlcv's
    # intracandle high. Pinning the absence prevents accidental
    # reintroduction.
    for name in dir(C):
        value = getattr(C, name)
        if isinstance(value, str):
            assert value != "/defi/history_price", (
                f"Stage 29.2 must not reference /defi/history_price; "
                f"saw constant {name}={value!r}"
            )


def test_allowed_paths_set_is_exactly_three():
    # Stage 29.2 owns two paths (price + ohlcv) for the price/ATH
    # adapter; Stage 30.4.3 added token_overview for the compact
    # market-context bridge. Any further endpoint expansion requires
    # a separately-authorized substage.
    assert C.BIRDEYE_ALLOWED_PATHS == (
        C.BIRDEYE_PATH_PRICE,
        C.BIRDEYE_PATH_OHLCV,
        C.BIRDEYE_PATH_TOKEN_OVERVIEW,
    )


def test_http_method_is_get_only():
    assert C.BIRDEYE_HTTP_METHOD_GET == "GET"


# ---------------------------------------------------------------------------
# Header pins
# ---------------------------------------------------------------------------


def test_header_api_key_name_pinned():
    assert C.BIRDEYE_HEADER_X_API_KEY == "X-API-KEY"


def test_header_x_chain_name_is_lowercase():
    # PHX1 production and Birdeye docs use lowercase ``x-chain``.
    assert C.BIRDEYE_HEADER_X_CHAIN == "x-chain"


def test_header_accept_name_pinned():
    assert C.BIRDEYE_HEADER_ACCEPT == "accept"


def test_x_chain_value_is_solana_constant():
    # Stage 29.2 is Solana-only by construction; the chain value
    # is a hardcoded constant -- no env-driven chain switch.
    assert C.BIRDEYE_X_CHAIN_VALUE_SOLANA == "solana"


def test_accept_value_is_application_json():
    assert C.BIRDEYE_ACCEPT_VALUE_JSON == "application/json"


def test_user_agent_pinned():
    assert C.BIRDEYE_USER_AGENT == "phx2-stage29-2/1"


# ---------------------------------------------------------------------------
# OHLCV resolution closed set
# ---------------------------------------------------------------------------


def test_default_ohlcv_type_is_15m():
    assert C.BIRDEYE_DEFAULT_OHLCV_TYPE == "15m"


def test_ohlcv_type_allowed_full_set():
    assert set(C.BIRDEYE_OHLCV_TYPE_ALLOWED) == {
        "1m", "3m", "5m", "15m", "30m",
        "1H", "2H", "4H", "6H", "8H", "12H",
        "1D", "3D", "1W", "1M",
    }


def test_is_allowed_ohlcv_type_accepts_default():
    assert C.is_allowed_ohlcv_type(C.BIRDEYE_DEFAULT_OHLCV_TYPE)


def test_is_allowed_ohlcv_type_rejects_unknown():
    assert not C.is_allowed_ohlcv_type("4m")
    assert not C.is_allowed_ohlcv_type("hourly")
    assert not C.is_allowed_ohlcv_type("")
    assert not C.is_allowed_ohlcv_type(None)
    assert not C.is_allowed_ohlcv_type(15)


# ---------------------------------------------------------------------------
# Bounded defaults
# ---------------------------------------------------------------------------


def test_default_timeout_is_30():
    assert C.DEFAULT_HTTP_TIMEOUT_SECONDS == 30


def test_timeout_bounds():
    assert C.MIN_HTTP_TIMEOUT_SECONDS == 1
    assert C.MAX_HTTP_TIMEOUT_SECONDS == 600


def test_default_lookback_hours_is_24():
    assert C.DEFAULT_LOOKBACK_HOURS == 24


def test_lookback_bounds():
    assert C.MIN_LOOKBACK_HOURS == 1
    assert C.MAX_LOOKBACK_HOURS == 168


def test_probe_max_requests_is_two():
    assert C.STAGE29_2_PROBE_MAX_REQUESTS == 2


# ---------------------------------------------------------------------------
# Safe-shape validators: base URL
# ---------------------------------------------------------------------------


def test_is_safe_base_url_accepts_https_prefix():
    # 8 chars "https://" + 4 chars host minimum = 12 total = min
    assert C.is_safe_base_url("https://aaaa")


def test_is_safe_base_url_rejects_http_prefix():
    assert not C.is_safe_base_url("http://example.com")


def test_is_safe_base_url_rejects_trailing_slash():
    assert not C.is_safe_base_url(
        "https://public-api.example.com/"
    )


def test_is_safe_base_url_rejects_too_short():
    assert not C.is_safe_base_url("https://x")


def test_is_safe_base_url_rejects_too_long():
    assert not C.is_safe_base_url(
        "https://" + ("a" * 300)
    )


def test_is_safe_base_url_rejects_unsafe_chars():
    assert not C.is_safe_base_url(
        "https://example.com/path?query=1"
    )
    assert not C.is_safe_base_url("https://a b.com")


def test_is_safe_base_url_rejects_non_string():
    assert not C.is_safe_base_url(None)
    assert not C.is_safe_base_url(12345)
    assert not C.is_safe_base_url(b"https://aaaa")


# ---------------------------------------------------------------------------
# Safe-shape validators: API key
# ---------------------------------------------------------------------------


def test_is_safe_api_key_accepts_alphanumeric():
    assert C.is_safe_api_key("abcdef0123456789ABCD")


def test_is_safe_api_key_accepts_dash_underscore():
    assert C.is_safe_api_key("aaaa-bbbb_cccc-dddd")


def test_is_safe_api_key_rejects_too_short():
    assert not C.is_safe_api_key("short")


def test_is_safe_api_key_rejects_too_long():
    assert not C.is_safe_api_key("a" * 1000)


def test_is_safe_api_key_rejects_punctuation():
    assert not C.is_safe_api_key("aaaa.bbbb.cccc.dddd")
    assert not C.is_safe_api_key("aaaa/bbbb/cccc/dddd")


def test_is_safe_api_key_rejects_non_string():
    assert not C.is_safe_api_key(None)
    assert not C.is_safe_api_key(12345)


# ---------------------------------------------------------------------------
# Safe-shape validators: mint
# ---------------------------------------------------------------------------


def test_is_safe_mint_accepts_solana_shaped():
    # 44-char base58 typical Solana mint
    mint = "So11111111111111111111111111111111111111112"
    assert C.is_safe_mint(mint)


def test_is_safe_mint_rejects_too_short():
    assert not C.is_safe_mint("abc")


def test_is_safe_mint_rejects_too_long():
    assert not C.is_safe_mint("a" * 100)


def test_is_safe_mint_rejects_punctuation():
    assert not C.is_safe_mint("So1111-1111111111111111111111111")


def test_is_safe_mint_rejects_non_string():
    assert not C.is_safe_mint(None)
    assert not C.is_safe_mint(b"So1111")


# ---------------------------------------------------------------------------
# Safe-shape validators: timeout + lookback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [1, 30, 600])
def test_is_safe_timeout_accepts_bounded(value):
    assert C.is_safe_timeout_seconds(value)


@pytest.mark.parametrize(
    "value", [0, -1, 601, "30", None, True, False, 1.5]
)
def test_is_safe_timeout_rejects(value):
    assert not C.is_safe_timeout_seconds(value)


@pytest.mark.parametrize("value", [1, 24, 168])
def test_is_safe_lookback_accepts_bounded(value):
    assert C.is_safe_lookback_hours(value)


@pytest.mark.parametrize(
    "value", [0, -1, 169, "24", None, True, False, 1.5]
)
def test_is_safe_lookback_rejects(value):
    assert not C.is_safe_lookback_hours(value)


# ---------------------------------------------------------------------------
# Safe source labels + reporting unit
# ---------------------------------------------------------------------------


def test_price_source_label_pinned():
    assert (
        C.BIRDEYE_PRICE_SOURCE_LABEL == "birdeye_defi_price"
    )


def test_ohlcv_source_label_pinned():
    assert (
        C.BIRDEYE_OHLCV_SOURCE_LABEL == "birdeye_defi_ohlcv"
    )


def test_reporting_unit_is_usd():
    assert C.BIRDEYE_REPORTING_UNIT_USD == "USD"


# ---------------------------------------------------------------------------
# Constants module ships NO URL host literal / raw secret
# ---------------------------------------------------------------------------


_FORBIDDEN_HOST_LITERALS: tuple[str, ...] = (
    "public-api.birdeye" + ".so",
    "birdeye" + ".so",
    "pro-api.birdeye" + ".so",
    "discord" + ".com",
    "helius" + ".xyz",
    "dexscreener" + ".com",
    "chainstack" + ".com",
)


def test_constants_module_carries_no_url_host_literal():
    import importlib
    src = importlib.import_module(
        "PHX2.stage29.birdeye_constants"
    ).__file__
    assert src is not None
    with open(src, "r", encoding="utf-8") as f:
        source = f.read()
    for needle in _FORBIDDEN_HOST_LITERALS:
        assert needle not in source, (
            f"birdeye_constants.py carries forbidden URL "
            f"host literal {needle!r}"
        )


_FORBIDDEN_RAW_SECRET_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "BIRDEYE_API" + "_KEY=",
    "BIRDEYE_API" + "_KEY:",
)


def test_constants_module_carries_no_raw_secret_literal():
    import importlib
    src = importlib.import_module(
        "PHX2.stage29.birdeye_constants"
    ).__file__
    assert src is not None
    with open(src, "r", encoding="utf-8") as f:
        source = f.read()
    for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
        assert needle not in source, (
            f"birdeye_constants.py carries forbidden raw-secret "
            f"literal {needle!r}"
        )
