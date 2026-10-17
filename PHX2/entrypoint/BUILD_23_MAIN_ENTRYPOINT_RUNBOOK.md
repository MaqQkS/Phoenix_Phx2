# Build #23 — `main.py` Supervised Entrypoint Runbook (DEPRECATED / HISTORICAL)

> **DEPRECATED — DO NOT RUN. This runbook is retained for history only.**
>
> The command surface it originally documented
> (`python main.py --mode private-supervised --live …`) is **no longer a
> supported armed path** and is not the way to arm a private-live send. It is
> superseded by the three canonical PowerShell launchers (below). The 2026-07-20
> residual re-audit recorded the old command surface as a competing, unmarked
> armed entry point (finding **M-3**); this banner and the rewrite below close it.
>
> Two facts make the old command inert as well as unsupported:
>
> - `python main.py` at the repository root now runs the **non-arming production
>   supervisor** (`PHX2.runtime.production_entrypoint`), whose parser accepts only
>   `--hours`, `--status`, and `--run-dir`. The documented `--mode
>   private-supervised --live` flags **argparse-error**; they cannot execute.
> - The supervisor's producer child **fails closed** and never arms or sends
>   (`run_producer_child` → `ARMED_PRIVATE_LIVE_REFUSED_USE_CANONICAL_LAUNCHERS`).
>   `python main.py --hours N` is observation/orchestration only.

---

## The canonical armed private-live path (and the only one)

The armed private-live send path is one of the three PowerShell launchers in
`C:\Users\BalaC\phx2_production_private_live`, and **only** those:

```
launch_pressure_24h_01.ps1     # 24 h
launch_soak_02h_01.ps1         # 2 h
launch_window_04.ps1           # 30 min
```

Each runs the **tracked repository module** from the repository root with the
complete production-gRPC contract:

| Argument | Value |
|---|---|
| module | `PHX2.free_tier_producer.free_tier_session` |
| provider mode | `--provider-mode paid_primary` |
| contract | `--require-production-grpc` (fails closed before any network object) |
| durable state | `--cursor-state-dir …\phx2_paid_primary_runtime\state` (stable) |
| ledger | `…\phx2_paid_primary_runtime\ledger\ping_dedupe.jsonl` |
| run output | `…\phx2_paid_primary_runtime\runs\<run-id>` (rotates) |
| HEAD pin | `--expected-head <repository HEAD>` |

`PHX2.free_tier_producer.launcher_contract.validate_launcher_arguments` checks
that whole vector offline, without starting anything. Operator arm
acknowledgement (the confirm token) is fetched and held only inside the launcher.

---

## What Build #23 was

Build #23 wired a thin `python main.py` launcher that validated operator inputs
and **subprocessed** an out-of-repo supervised private-operator flow. It imported
no supervisor, built no second send path, constructed no transport, flipped no
arm, and sent nothing itself; `--live` only *launched* the out-of-repo flow.

That entrypoint has been superseded. The repository root `main.py` is now the
non-arming production supervisor described in the banner above, and the armed
private-live path is exclusively the three launchers. The supervised-launcher
modules under `PHX2/entrypoint/` remain in the tree with their own tests, but no
operator command surface documents an armed run through them, and none is
supported.

---

## Verification (offline, no send)

```powershell
# Non-arming supervisor status (read-only; constructs nothing, sends nothing):
python main.py --status

# The offline launcher-argument contract (checks the canonical vector without
# starting anything):
python -m pytest PHX2/tests/test_production_launch_contract.py -q
```

Do **not** attempt to arm a private-live send through `main.py`. The armed path
is a canonical launcher, run interactively by the operator, and only that.
