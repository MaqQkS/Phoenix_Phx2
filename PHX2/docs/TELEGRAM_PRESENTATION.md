# PHX2 Telegram presentation and operational handoff

## Implemented presentation

The current PHX1 `TelegramSender.send_dip_alert` uses a token logo from the
already-fetched overview `logoURI`. With its image flag enabled, Pillow makes an
opaque 1000×200 banner: a blurred, darkened logo background and a centered logo
bounded to 170×170. This is a logo banner, not a chart. Its active formatter has
the token/tier, mint, State metrics and Global Fees; there are no inline buttons.
This was verified from source, not from a live Telegram send or a screen.

PHX2 now uses the same compact visual arrangement while keeping its own metric
meanings. Its volume remains the measured five-minute gross/net volume; it does
not invent PHX1 volume trends, LP ratings, fees or other unavailable metrics.
Missing values remain unavailable. Source, ATH coverage, risk and required
shadow-policy review stay visible. Detailed fee/Ante/Builder evidence stays in
the existing compose artifact. Every message says it is a **discovery alert**;
it is not a paper entry/exit notification or a claim that a fill happened.

Images are optional, controlled by `PHX2_TELEGRAM_COIN_IMAGES_ENABLED=true`.
The default is false; no external configuration was changed. The image URL rides
the existing exact-mint paid overview, through the scheduler, into a bounded
in-memory cache keyed by mint. Restart refills that optional cache through normal
overview refreshes; it does not make a separate metadata/provider request.

The delivery boundary accepts public HTTPS images only, pins the resolved public
IP while validating TLS against the original hostname, rejects redirects and
credential/query/fragment-bearing URLs, bounds input bytes and decoded dimensions,
and logs closed status tokens rather than URLs or image bytes. The logo download
is an additional public-image HTTP request only when images are enabled and a
valid URL plus Pillow are available. No such request was made during this work.

Missing/invalid logos, missing Pillow, decode/download failures, or captions over
1024 UTF-16 units fall back to one text message. Confirmed photo rejection can
fall back to text. Timeouts, malformed acknowledgements, and server failures never
trigger a second send; the existing delivery journal holds ambiguous outcomes for
reconciliation. Explicit rate limits retain bounded retry. No buttons were added,
matching PHX1's active path.

## Review and validation

`PHX2/scripts/phx2_preview_telegram.py` creates a self-contained HTML review from
synthetic data without reading configuration or using the network. The captions
use the production composer, and the PAPER entry, recovery and exit cards use
the production notification formatter. After the supplied explicit authorization,
the identical Pillow installation retry succeeded in the project `.venv` only.
The verified version is **Pillow 13.0.0**. The production renderer produced a
1000x200 RGB PNG (31,308 bytes) from a synthetic local logo; the HTML now embeds
that actual image. All 40 presentation tests passed with the offline network
guard enabled, including real rendering, malformed-image handling and fallback.
This verifies local rendering only; image delivery remains separately armed.

## Operational implementation and verification limits

The local implementation now includes structurally proven migration admission
without lowercase-suffix dependence; bounded pricing-tail retention with paper
coverage feedback; and coherent snapshot context for eligibility, activation,
risk, quote time and as-of ATH. Exact mint case and policy filters remain
meaningful. The final integrated offline scope passed **509 tests with no skips**
after Pillow installation. Separate scopes passed 135 final admission
tests, 371 recovery/checkpoint/epoch tests and 393 scheduler/provider-ownership
tests; these scopes overlap and must not be summed. Independent source review
reported no remaining concrete P1/P2 finding within its reviewed scope.

Paper lifecycle state, checkpoints, fill/notification dedupe and projection
recovery are wired through canonical `paper_state.json`, with a single-run lease
and cooperative stop/resume. Input selection is bound to canonical state.
`--allow-input-rollover` permits only adding roots while retaining every old
root in `--inputs`, up to 16 total; missing/replaced consumed files are refused.
The 24 MiB canonical-state limit stops before committing an oversized state.
Legacy live ledgers without canonical state need a reviewed migration or a
separately reviewed new canary. Net full-cost recovery at 1.35x and the fixed 30%
runner trail remain the approved BALA behavior.

Clearly labelled `PAPER` entry, stake-recovery and final-exit notifications now
have durable event/delivery state, separate from discovery mint/tier dedupe.
They remain **outbox-only by default**. Real delivery requires explicit arming,
a small positive message limit, reviewed destination hash/confirmation, and
separate paper-only credentials. Ambiguous outcomes remain held for review;
they must not be blindly resent. Discovery alerts still do not imply paper fills.

Repository-owned preflight and launcher wiring are inactive and report-only.
They check reviewed code pins, explicit source selection, output separation,
recovery configuration, bounded budgets and pricing capacity. The audited
six-strategy worst-case exposure of 135 exceeds the 32-slot tail; an explicit
reviewed canary configuration/capacity decision is still required. No external
configuration has been changed to resolve that mismatch.

See [PAPER_CANARY_RUNBOOK.md](PAPER_CANARY_RUNBOOK.md) for source-root rollover,
state limits, deployment pins, separate owners, destination/budget decisions,
provider capabilities and the later bounded canary acceptance checks. After
explicit approval, all seven additional Helius asyncio cases passed with fake
provider transports and Windows loopback only: zero non-loopback attempts and
14 local socket operations. The 509-test integrated scope and these seven cases
are separate verified scopes. Actual external deployment and authorized live
provider/Telegram checks remain outstanding. Synthetic outcomes and passing
unit tests alone do not establish live readiness or profitability.

No PHX1 files or database were changed or opened by the implementation. No live
producer, paper engine or Telegram sender was started. No credentials, deployment
configuration or provider settings were changed.
