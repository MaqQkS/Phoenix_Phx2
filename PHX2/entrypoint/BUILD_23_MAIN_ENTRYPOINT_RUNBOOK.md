# Build #23 — Safe `main.py` Supervised Entrypoint Runbook

Build #23 wires a **safe `python main.py` entrypoint** to the already-proven,
**out-of-repo supervised private operator flow**. `main.py` is a thin launcher: it
validates operator inputs and **subprocesses** the supervisor. It imports no
supervisor, builds no second send path, constructs no transport, flips no arm, and
sends nothing. `--live` only *launches* the supervised flow; the interactive human
approval, the one-line arm flip, and the single private operator send all remain
**inside the out-of-repo supervisor**.

> This build performs **no send, no arm, no durable-ledger mutation**. The default
> `python main.py` is no-send / status-only.

---

## 1. Command surface

```
python main.py
python main.py --mode private-supervised --preflight-only \
    --require-baseline <sha256>:<size_bytes>:<line_count>
python main.py --mode private-supervised --dry-run \
    --require-baseline <sha256>:<size_bytes>:<line_count>
python main.py --mode private-supervised --live --post-send stop \
    --require-baseline <sha256>:<size_bytes>:<line_count>
```

- **Default (`python main.py`)** — prints a one-line safe status and exits `0`.
  Never reaches the launcher, never reads a credential, never spawns a process.
- **`--mode private-supervised`** — the only accepted mode. Requires exactly one
  action and a `--require-baseline` assertion.
- **`--preflight-only`** — invokes the supervisor's preflight verb (policy gate +
  durable dedupe forecast). No send.
- **`--dry-run`** — invokes the supervisor's dry-run verb (preview + send-fake +
  dedupe forecast). No real transport.
- **`--live --post-send stop`** — *launches* the supervised live flow. The
  supervisor still performs interactive human approval, the one-line arm flip, the
  single private send, immediate re-safe, the +1 ledger verification, and the
  baseline update. `--post-send stop` is required with `--live`.

Exit codes: `0` default safe / relayed child success · child exit code relayed for
an invoked supervisor · `3` fail-closed launcher refusal · `2` argparse usage error.

---

## 2. Durable-ledger baseline assertion (exact semantics)

`--require-baseline` carries the operator's durable JSONL ledger baseline as
**`sha256:size_bytes:line_count`**:

| Field | Meaning |
|---|---|
| `sha256` | the durable ledger content digest (64 hex chars, case preserved) |
| `size_bytes` | the durable ledger size in **bytes** |
| `line_count` | the durable ledger **line / JSONL record** count |

**Current baseline:**

```
78D20A7A2FE69BEF8BF833B60BB92209D06D23CE69A8D6F2800F991AC0331D96 / 1096 bytes / 3 lines
```

Current preflight example:

```
python main.py --mode private-supervised --preflight-only \
    --require-baseline 78D20A7A2FE69BEF8BF833B60BB92209D06D23CE69A8D6F2800F991AC0331D96:1096:3
```

**After a successful next real send** (owned by the out-of-repo supervisor, not by
this repo):

- `line_count` advances **3 → 4** (one appended JSONL record),
- `size_bytes` grows by **one JSONL record** (not by exactly +1 byte),
- `sha256` **changes** and becomes the new baseline.

`main.py` only **passes the triple through verbatim** to the supervisor and
verifies its shape. It computes no digest, reads no ledger, and mutates no ledger.
The supervisor verifies the live ledger against the baseline before arming and
re-verifies the advanced baseline after a successful send.

---

## 3. Supervisor command pointer (`PHX2_SUPERVISOR_CMD`)

`main.py` resolves *where* the out-of-repo supervisor lives from a single owned
**pointer** env var (a command location — **not** a credential):

```
# A single executable / launcher path:
$env:PHX2_SUPERVISOR_CMD = "C:\path\to\supervisor.exe"

# Or a JSON argv array (interpreter + script + any prefix args):
$env:PHX2_SUPERVISOR_CMD = '["python", "C:\\path\\to\\supervisor.py"]'
```

If `PHX2_SUPERVISOR_CMD` is unset, blank, or malformed, every `--mode
private-supervised` action **fails closed** (exit `3`) and no subprocess is spawned.

The supervisor inherits the real environment and stdio when launched, so **it** —
not `main.py` — reads its own credentials and runs its own interactive approval.
`main.py` reads no credential env var.

---

## 4. Handoff contract (argv `main.py` appends to the supervisor command)

`main.py` appends only this closed-set tail to the resolved command prefix:

```
--mode private-supervised --action <preflight-only|dry-run|live> \
    --require-baseline <sha256>:<size_bytes>:<line_count> [ --post-send stop ]
```

`--post-send stop` is appended only for `--live`. No routing, audience, arm,
transport, or credential flag is ever appended. The out-of-repo supervisor must
accept this contract.

---

## 5. Safety invariants

- Default `python main.py` is no-send / status-only.
- `main.py` subprocesses the supervisor; it never imports it and builds no second
  send path.
- `main.py` constructs no transport, passes no authorization sentinel, and flips no
  arm. `--live` only launches the supervised flow.
- The only accepted mode is `private-supervised`; there is no public / subscriber /
  paid routing path.
- `main.py` reads exactly one env var (the supervisor command pointer) and never a
  credential.
- `main.py` prints only a redacted baseline (first/last 8 hex chars) and closed-set
  status tokens — never the full digest, the handoff argv, or any secret.
- `_ARMED_REAL_SEND_WIRING_REVIEWED` (in `supervised_launcher.py`) stays `False`:
  this repo ships no reviewed real-send wiring of its own.

---

## 6. Verification (offline, no send)

```powershell
# Build #23 entrypoint test subset (fakes only; never spawns a process):
python -m pytest PHX2/tests/entrypoint -q

# Default safe status:
python PHX2/main.py
```

Do **not** run `--mode private-supervised --live` as part of verification: it is the
real supervised ceremony and is gated by interactive human approval inside the
out-of-repo supervisor.
