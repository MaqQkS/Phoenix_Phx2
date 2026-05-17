"""Stage 20.4 -- no forbidden network/dispatch imports anywhere in
PHX2/stage20/ (inner + outer scope combined)."""

from __future__ import annotations

from pathlib import Path

from PHX2.stage20.closure import codebase_auditor as ca


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for ancestor in [p, *p.parents]:
        candidate = (
            ancestor / "PHX2" / "stage20" / "closure" / "__init__.py"
        )
        if candidate.is_file():
            return ancestor
    raise RuntimeError(f"could not locate PHX2 repo root from {p}")


def test_phx2_stage20_has_no_forbidden_network_imports():
    """The combined inner+outer scope bucket
    ``forbidden_network_imports`` must be empty (covers
    requests/httpx/aiohttp/urllib3/websockets/grpc/grpclib/
    discord/telegram/telethon/pyrogram/dotenv/git/pygit2/dulwich)."""
    result = ca.audit_codebase(_repo_root())
    assert result.forbidden_network_imports == (), (
        f"network/dispatch import hits: "
        f"{result.forbidden_network_imports}"
    )
