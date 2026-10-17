"""Deterministically deploy the external ``launch_live_24x7.ps1``.

The launcher is operator glue and lives OUT of the repository, but it must be
reproducible byte-for-byte from tracked source.  This script renders it from
:mod:`PHX2.watchdog.launcher_template`, validates the rendered text against the
Stage-10 launcher contract, and only then writes it.

Default is a DRY RUN: it prints the deployment specification (bytes, sha256,
pins, contract refusals) and writes nothing.  ``--write`` performs the
deployment.  Nothing secret is read or written; no producer is started.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PHX2.free_tier_producer.compat import build29_cap1_ledger as ledgerlib  # noqa: E402
from PHX2.free_tier_producer.launcher_contract import CANONICAL_LEDGER_PATH  # noqa: E402
from PHX2.watchdog.config import (  # noqa: E402
    CANONICAL_LIVE_LAUNCHER_PATH,
    resolve_repo_head,
)
from PHX2.watchdog.launcher_template import (  # noqa: E402
    deployment_specification,
    render_live_launcher_bytes,
    validate_live_launcher_text,
)


def _default_baseline() -> Optional[str]:
    triple = ledgerlib.compute_baseline(CANONICAL_LEDGER_PATH)
    return triple.as_token() if triple is not None else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m PHX2.scripts.phx2_deploy_live_launcher",
        description="Render and deploy the canonical launch_live_24x7.ps1.")
    parser.add_argument("--expected-head", default=None,
                        help="commit to pin (default: current repository HEAD)")
    parser.add_argument("--ledger-baseline", default=None,
                        help=("paid-ledger baseline triple to pin (default: "
                              "the canonical ledger's current baseline)"))
    parser.add_argument("--target", default=CANONICAL_LIVE_LAUNCHER_PATH,
                        help="where to write the launcher")
    parser.add_argument("--write", action="store_true",
                        help="actually write the launcher (default: dry run)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    head = (str(args.expected_head or "").strip().lower()
            or (resolve_repo_head(REPO_ROOT) or ""))
    if len(head) != 40:
        print("[refused] EXPECTED_HEAD_UNRESOLVED")
        return 2
    baseline = str(args.ledger_baseline or "").strip() or _default_baseline()
    if not baseline:
        print("[refused] LEDGER_BASELINE_UNRESOLVED "
              "(canonical ledger not readable)")
        return 2

    body = render_live_launcher_bytes(
        expected_head=head, ledger_baseline=baseline)
    refusals = validate_live_launcher_text(
        body.decode("utf-8"), expected_head=head, ledger_baseline=baseline)
    spec = deployment_specification(
        expected_head=head, ledger_baseline=baseline)
    print(json.dumps(spec, indent=2, sort_keys=True))
    if refusals:
        print("[refused] LIVE_LAUNCHER_CONTRACT_REFUSED: "
              + ", ".join(refusals))
        return 2

    target = Path(str(args.target))
    existing = None
    if target.exists():
        existing = hashlib.sha256(target.read_bytes()).hexdigest()
        print(f"existing_sha256={existing}")
        print(f"existing_bytes={target.stat().st_size}")
    print(f"rendered_sha256={spec['sha256']}")
    print(f"rendered_bytes={spec['bytes']}")
    print(f"identical={existing == spec['sha256']}")

    if not args.write:
        print("dry_run=True (pass --write to deploy)")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(body)
    tmp.replace(target)
    written = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"written_sha256={written}")
    print(f"deployment_verified={written == spec['sha256']}")
    return 0 if written == spec["sha256"] else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
