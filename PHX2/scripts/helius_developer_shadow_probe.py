"""Operator CLI for the bounded Helius Developer no-send/shadow proof.

This script has no production-launch or transport imports.  It prints sanitized
JSON only and never writes provider responses or production runtime evidence.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List, Tuple

from PHX2.free_tier_producer.migration_admission import (
    PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_PROGRAM_ID,
)
from PHX2.shadow_probes.helius_developer import (
    DEFAULT_MAX_RAW_BYTES,
    FILTER_CONTROL,
    FILTER_TIGHT,
    PUMPSWAP_PROGRAM_ID,
    classify_decoder_update,
    load_helius_probe_config,
    offline_filter_match,
    project_credits,
    resolved_update_account_texts,
    run_http_capability_probe,
    run_live_comparison,
    run_slot_range_recovery,
    run_wss_capability_probe,
)
from PHX2.tests.test_migrate_v2_genuine_migrations import (
    GENUINE_MIGRATIONS,
    _build_real_migrate_v2_update,
)
from PHX2.tests.test_migration_admission import build_pool_creation_update


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPOSITORY_ROOT / ".env"
SHADOW_ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts" / "helius_developer_shadow"


def _fixture_matrix() -> Iterable[Tuple[str, str, str, object]]:
    """Every authoritative valid migration plus decoder edge populations."""

    yield (
        "synthetic_migrate_legacy_inner",
        "migrate",
        "legacy",
        build_pool_creation_update(),
    )
    yield (
        "synthetic_migrate_v2_legacy_inner",
        "migrate_v2",
        "legacy",
        build_pool_creation_update(
            migrate_discriminator=PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR
        ),
    )
    yield (
        "synthetic_migrate_v2_v0_loaded_addresses",
        "migrate_v2",
        "v0",
        build_pool_creation_update(
            migrate_discriminator=PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
            use_loaded_addresses=True,
        ),
    )
    yield (
        "synthetic_wrapped_migrate_v2_inner_ancestry",
        "migrate_v2",
        "legacy",
        build_pool_creation_update(
            shape="WRAPPED",
            migrate_discriminator=PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
        ),
    )
    for index, row in enumerate(GENUINE_MIGRATIONS, start=1):
        yield (
            f"preserved_20260718_migrate_v2_{index}",
            "migrate_v2",
            "legacy",
            _build_real_migrate_v2_update(*row),
        )
    yield (
        "failed_migration_excluded",
        "failed_migration",
        "legacy",
        build_pool_creation_update(failed=True),
    )
    yield (
        "direct_pool_creation_not_migration",
        "direct_pool",
        "legacy",
        build_pool_creation_update(shape="DIRECT"),
    )
    yield (
        "malformed_short_create_pool",
        "malformed",
        "legacy",
        build_pool_creation_update(short_accounts=True),
    )
    unknown = build_pool_creation_update(
        migrate_discriminator=b"\x01\x02\x03\x04\x05\x06\x07\x08"
    )
    yield (
        "unknown_migration_discriminator",
        "malformed",
        "legacy",
        unknown,
    )
    non_migration = build_pool_creation_update()
    message = non_migration.transaction.transaction.transaction.message
    meta = non_migration.transaction.transaction.meta
    message.instructions = [
        SimpleNamespace(program_id_index=0, accounts=b"", data=b"ordinary")
    ]
    meta.inner_instructions = []
    yield (
        "ordinary_non_migration_transaction",
        "non_migration",
        "legacy",
        non_migration,
    )
    vote = build_pool_creation_update()
    vote.is_vote = True
    yield ("vote_transaction_excluded", "vote", "legacy", vote)
    yield ("malformed_missing_transaction", "malformed", "unknown", object())


def run_offline_recall() -> Dict[str, object]:
    rows: List[Dict[str, object]] = []
    valid = 0
    control_valid = 0
    tight_valid = 0
    for source, migration_type, version, update in _fixture_matrix():
        accounts = set(resolved_update_account_texts(update))
        local = classify_decoder_update(update)
        control = offline_filter_match(update, filter_label=FILTER_CONTROL)
        tight = offline_filter_match(update, filter_label=FILTER_TIGHT)
        is_valid = local.classification in ("migrate", "migrate_v2")
        # Failed/vote fixtures deliberately prove the server exclusions even if
        # their underlying transaction body is migration-shaped.
        if migration_type in ("failed_migration", "vote"):
            is_valid = False
        if is_valid:
            valid += 1
            control_valid += int(control)
            tight_valid += int(tight)
        rows.append(
            {
                "source_fixture": source,
                "migration_type": migration_type,
                "transaction_version": version,
                "pump_account_present": PUMPFUN_PROGRAM_ID in accounts,
                "pumpswap_account_present": PUMPSWAP_PROGRAM_ID in accounts,
                "required_accounts_present": (
                    PUMPFUN_PROGRAM_ID in accounts
                    and PUMPSWAP_PROGRAM_ID in accounts
                ),
                "control_match": control,
                "tight_match": tight,
                "local_decoder_result": local.classification,
                "local_decoder_reject_reason": local.reject_reason,
            }
        )
    return {
        "authoritative_fixture_count": len(rows),
        "authoritative_valid_migrations": valid,
        "control_valid_recall_count": control_valid,
        "control_valid_recall_percent": (
            control_valid * 100 / valid if valid else None
        ),
        "tight_valid_recall_count": tight_valid,
        "tight_valid_recall_percent": (
            tight_valid * 100 / valid if valid else None
        ),
        "tight_approved_offline": bool(valid and tight_valid == valid),
        "fixtures": rows,
    }


def _config(args: argparse.Namespace):
    return load_helius_probe_config(env_path=Path(args.env_file))


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _write_live_artifact(output: Path, payload: Dict[str, object]) -> Dict[str, object]:
    resolved = output.resolve()
    try:
        resolved.relative_to(SHADOW_ARTIFACT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            "live output must remain under artifacts/helius_developer_shadow"
        ) from exc
    resolved.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with resolved.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
    relative = resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    return {
        "sanitized_artifact": relative,
        "sanitized_artifact_bytes": len(serialized.encode("utf-8")),
        "sanitized_artifact_sha256": hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded Helius Developer no-send/shadow capability proof"
    )
    parser.add_argument(
        "--env-file", default=str(DEFAULT_ENV_PATH), help=argparse.SUPPRESS
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("env")
    sub.add_parser("offline")
    sub.add_parser("capability")
    live = sub.add_parser("live")
    live.add_argument("--seconds", type=int, default=600)
    live.add_argument("--max-raw-bytes", type=int, default=DEFAULT_MAX_RAW_BYTES)
    live.add_argument("--output", type=Path)
    recovery = sub.add_parser("recovery")
    recovery.add_argument(
        "--kind", choices=("known", "gap", "empty"), default="known"
    )
    recovery.add_argument("--page-size", type=int, default=25)
    recovery.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()

    if args.command == "offline":
        _print(run_offline_recall())
        return 0

    config = _config(args)
    if args.command == "env":
        _print(config.sanitized_presence())
        return 0
    if args.command == "capability":
        result = {
            "environment": config.sanitized_presence(),
            "http": asdict(run_http_capability_probe(config)),
            "wss": asdict(asyncio.run(run_wss_capability_probe(config))),
        }
        _print(result)
        return 0
    if args.command == "live":
        result = asyncio.run(
            run_live_comparison(
                config,
                duration_seconds=args.seconds,
                max_raw_bytes=args.max_raw_bytes,
            )
        )
        payload = asdict(result)
        payload["control_projection"] = project_credits(
            byte_count=int(result.control["raw_uncompressed_bytes"]),
            elapsed_seconds=result.elapsed_seconds,
        )
        payload["tight_projection"] = project_credits(
            byte_count=int(result.tight["raw_uncompressed_bytes"]),
            elapsed_seconds=result.elapsed_seconds,
        )
        if args.output is not None:
            notification_evidence = payload.pop("evidence")
            artifact_payload = {
                "schema_version": 1,
                "summary": payload,
                "notifications": notification_evidence,
            }
            payload.update(_write_live_artifact(args.output, artifact_payload))
            payload["sanitized_notification_evidence_count"] = len(
                notification_evidence
            )
        _print(payload)
        return 0
    if args.command == "recovery":
        known = GENUINE_MIGRATIONS[0]
        known_slot = int(known[8])
        known_signature = str(known[9])
        if args.kind == "known":
            lower = upper = known_slot
            signature = known_signature
        elif args.kind == "gap":
            lower, upper = known_slot - 2, known_slot + 2
            signature = known_signature
        else:
            lower = upper = 0
            signature = None
        result = run_slot_range_recovery(
            config,
            address=PUMPFUN_PROGRAM_ID,
            slot_gte=lower,
            slot_lte=upper,
            page_size=args.page_size,
            max_pages=args.max_pages,
            known_signature=signature,
            repeat_first_page=True,
        )
        _print(asdict(result))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
