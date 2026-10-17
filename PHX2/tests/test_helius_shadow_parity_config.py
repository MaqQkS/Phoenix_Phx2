"""Deterministic tests for the standalone parity configuration boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from PHX2.scripts import helius_shadow_parity_config as config


HELIUS_FILE_KEY = "helius-file-secret"
HELIUS_PROCESS_KEY = "helius-process-secret"
CHAINSTACK_FILE_TOKEN = "chainstack-file-token"
CHAINSTACK_PROCESS_TOKEN = "chainstack-process-token"
RPC_BASE = "https://mainnet.helius-rpc.com/"
WS_BASE = "wss://mainnet.helius-rpc.com/"
CHAINSTACK_ENDPOINT = "fixture.example:443"


def _dotenv(
    *,
    endpoint: str = CHAINSTACK_ENDPOINT,
    token: str = CHAINSTACK_FILE_TOKEN,
    include_endpoint: bool = True,
    include_token: bool = True,
) -> str:
    lines = [
        f"HELIUS_API_KEY={HELIUS_FILE_KEY}",
        f"HELIUS_RPC_URL={RPC_BASE}",
        f"HELIUS_WS_URL={WS_BASE}",
        "HELIUS_GRPC_ENDPOINT=legacy.chainstack.example:443",
    ]
    if include_endpoint:
        lines.append(
            "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT=" + endpoint
        )
    if include_token:
        lines.append(
            "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN=" + token
        )
    return "\n".join(lines) + "\n"


def _load(path: Path, *, environ=None):
    return config.load_shadow_parity_configuration(
        env_path=path,
        environ={} if environ is None else environ,
        max_helius_raw_bytes=256_000_000,
    )


def test_both_provider_configs_load_from_dotenv(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(_dotenv(), encoding="utf-8")
    resolved = _load(path)
    assert resolved.sanitized_presence() == {
        "CHAINSTACK_ENDPOINT": "PRESENT",
        "CHAINSTACK_TOKEN": "PRESENT",
        "HELIUS_API_KEY": "PRESENT",
        "HELIUS_RPC_URL": "PRESENT",
        "HELIUS_WS_URL": "PRESENT",
        "HELIUS_GRPC_ENDPOINT": "PRESENT_LEGACY_IGNORED",
    }
    assert resolved.sanitized_readiness() == {
        "SHADOW_AUTH_PRESENT": "true",
        "SHADOW_RPC_BASE_CONFIGURED": "true",
        "SHADOW_STREAM_BASE_CONFIGURED": "true",
        "CONTROL_SOURCE_CONFIGURED": "true",
        "CONTROL_AUTH_PRESENT": "true",
        "LEGACY_ALIAS_IGNORED": "true",
    }
    assert resolved.helius.api_key.reveal() == HELIUS_FILE_KEY


def test_process_environment_overrides_dotenv(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        _dotenv(endpoint="unsafe endpoint", token="bad token"),
        encoding="utf-8",
    )
    resolved = _load(
        path,
        environ={
            "HELIUS_API_KEY": HELIUS_PROCESS_KEY,
            "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT": (
                CHAINSTACK_ENDPOINT
            ),
            "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN": (
                CHAINSTACK_PROCESS_TOKEN
            ),
        },
    )
    assert resolved.helius.api_key.reveal() == HELIUS_PROCESS_KEY


def test_explicit_empty_process_value_overrides_file_and_refuses(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    path.write_text(_dotenv(), encoding="utf-8")
    with pytest.raises(
        config.ShadowParityConfigurationError,
        match="CHAINSTACK_ENDPOINT_MISSING",
    ):
        _load(
            path,
            environ={
                "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT": ""
            },
        )


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    (
        ({"include_endpoint": False}, "CHAINSTACK_ENDPOINT_MISSING"),
        ({"include_token": False}, "CHAINSTACK_TOKEN_MISSING"),
        (
            {"endpoint": "https://user:secret@example.invalid:443"},
            "CHAINSTACK_ENDPOINT_UNSAFE",
        ),
    ),
)
def test_chainstack_configuration_refusals_are_value_free(
    tmp_path: Path, kwargs: dict, reason: str
) -> None:
    path = tmp_path / ".env"
    raw = _dotenv(**kwargs)
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(config.ShadowParityConfigurationError) as caught:
        _load(path)
    assert caught.value.reason == reason
    rendered = repr(caught.value) + str(caught.value)
    for secret in (
        HELIUS_FILE_KEY,
        CHAINSTACK_FILE_TOKEN,
        "user:secret",
    ):
        assert secret not in rendered


def test_secret_values_and_completed_urls_never_render(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    path.write_text(_dotenv(), encoding="utf-8")
    resolved = _load(path)
    completed_rpc = RPC_BASE + "?api-key=" + HELIUS_FILE_KEY
    completed_ws = WS_BASE + "?api-key=" + HELIUS_FILE_KEY
    rendered = (
        repr(resolved)
        + repr(resolved.helius)
        + repr(resolved.chainstack)
        + repr(resolved.sanitized_presence())
    )
    for secret in (
        HELIUS_FILE_KEY,
        CHAINSTACK_FILE_TOKEN,
        completed_rpc,
        completed_ws,
    ):
        assert secret not in rendered


def test_dotenv_is_never_modified(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(_dotenv(), encoding="utf-8")
    before = (
        hashlib.sha256(path.read_bytes()).hexdigest(),
        path.stat().st_size,
        path.stat().st_mtime_ns,
    )
    _load(path)
    after = (
        hashlib.sha256(path.read_bytes()).hexdigest(),
        path.stat().st_size,
        path.stat().st_mtime_ns,
    )
    assert after == before


def test_legacy_grpc_alias_is_presence_only_and_never_a_helius_url(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    path.write_text(_dotenv(), encoding="utf-8")
    resolved = _load(path)
    assert resolved.legacy_chainstack_alias_present is True
    assert resolved.helius.rpc_base_url.reveal() == RPC_BASE
    assert resolved.helius.ws_base_url.reveal() == WS_BASE


def test_dotenv_values_are_trimmed_before_both_configs_are_built(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    padded = _dotenv().replace("=", "=  ").replace("\n", "  \n")
    path.write_text(padded, encoding="utf-8")
    resolved = _load(path)
    assert resolved.helius.api_key.reveal() == HELIUS_FILE_KEY
    assert (
        resolved.helius.rpc_base_url.reveal() == RPC_BASE
    )
    assert (
        resolved.helius.ws_base_url.reveal() == WS_BASE
    )
