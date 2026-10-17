# Paper stake recovery at 1.35x

The example/default run and the operator's external paper config now request
initials recovery at 1.35x raw blended entry price, then a 30% trail from the
post-recovery peak. The legacy strategy parameter defaults remain compatible
with older explicit configs; omission still disables recovery.

Recovery targets total contributed USD, including buy fees and every prior DCA
leg. The sale solver uses the same net fill model as execution: sell fees,
slippage, and impact calculated on the actual gross token-sale notional.
It searches increasing portions of the capped impact curve and uses only a
sub-cent floating-point cushion. This is simulated execution, not a promise
that future market orders can realize the same proceeds.

The strategy emits an intent without marking principal recovered. After the
fill is recorded, the engine accumulates actual net proceeds, confirms recovery
only when the total covers cost, and arms the runner. A net shortfall remains
explicit and a later attempt requests only the missing amount. Missing/dead
liquidity, insufficient proceeds, or invalid fills cannot claim recovery.
Recovery is deferred if it would consume all remaining tokens. A failed fill
append does not mutate the position or arm a runner. Existing multi-file ledger
writes are not an atomic transaction; this change does not claim general crash
recovery across an interruption between a fill append and a position write.

When recovery is enabled, it takes precedence over new DCA exposure and over
the high-quality 5x trim/25% trail, including old saved HQ plans. Other stop-loss,
rug, data-loss and maximum-hold rules remain active. The separate three-times
strategy retains its configured trigger but uses the corrected recovery
accounting too.

## Verification

Base: `78bdea67118544d3385bd325d8c72172715b9935`.
Branch: `fix/paper-net-stake-recovery-135x`.

- Baseline paper suite: **165 passed**.
- Patched paper suite: **188 passed**, no failures or skips.
- Coverage includes 1.35x boundaries, uncapped/capped impact, buy and sell
  costs, DCA principal, a retained runner, HQ trail behavior, adverse/zero-net
  fill injection, append failure, shortfall retry after restart, saved peak,
  and preservation of stop-loss/rug/time/data-loss exits.
- The comparison script is included in the paper package's existing static
  import/capability safety checks.

Run from the repository root with the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pytest PHX2/tests/paper_trading -q --basetemp=.pytest_basetmp_net_recovery_review -p no:cacheprovider
```

## Paired offline replay

The new `PHX2/scripts/phx2_compare_paper_exits.py` compares a flat +35% full
exit with the recovery policy using identical input observations and costs.
For this requested comparator, the old HQ 5x exception is disabled. Historical
entry gates and sizing otherwise remain intact. No final ATH checkpoint is
overlaid onto earlier records, and no prices are generated or interpolated in
the historical cases. Both books leave positions open at end-of-stream;
any reported open-position net liquidation is valuation, not a simulated fill.

Sources were existing `pricing_tail.jsonl` plus `candidates/*.jsonl` from
`C:\Users\BalaC\phx2_paid_primary_runtime\runs`:

| Run suffix | Normalized observations | Priced | Explicit tier | ATH market-cap context | Maximum explicit price age |
|---|---:|---:|---:|---:|---:|
| 20260803T171355Z | 32 | 32 | 1 | 25 | 47 seconds |
| 20260803T024439Z | 1,909 | 1,822 | 0 | 0 | 2,474 seconds |
| 20260802T160009Z | 16,238 | 4,049 | 0 | 10 | 12,561 seconds |

All three historical pairs produced **zero Bala entries** and therefore no
exit comparison. The newest run records an MC-floor risk rejection; the older
streams include missing ATH/tier context and repeated freshness rejections.
This is not evidence of either policy's historical profitability. No PHX1
database, original or exported, was needed or opened.

The synthetic cases below use an identical $100 entry, $50,000 liquidity,
score 0.95, no DCA, and 60-second observations in each book. Costs match the
operator config: 150 bps base slippage, 100 bps fees, impact of 30 bps per 1%
of LP, capped at 800 bps. All positions in these cases closed; values are
realized net PnL, rounded to four decimals.

| Synthetic price path, multiples of entry | Full exit +35% | Recover and ride |
|---|---:|---:|
| 1, 1.35, 2, 3, 2.09 | $28.2240 | $43.7454 |
| 1, 1.35, 1, 0.94 | $28.2240 | $19.6779 |
| 1, 1.35, 0.60 | $28.2240 | $12.5609 |
| 1, 1.2, 0.69 | -$34.4376 | -$34.4376 |
| 1, 1.35, 5, 3.6, 3.5 | $28.2240 | $73.2444 |

Each triggered synthetic recovery returned $100 net and retained a runner.
The policy gives up some early realized profit in exchange for remaining
exposure. A trailing threshold is evaluated at the next available observation;
gaps can produce a worse exit than the threshold price.

Reproduce into a new output directory (existing directories are refused):

```powershell
.\.venv\Scripts\python.exe -m PHX2.scripts.phx2_compare_paper_exits --config C:\Users\BalaC\phx2_paper_trading\paper_config.json --run-dir C:\Users\BalaC\phx2_paid_primary_runtime\runs\paid_primary_live_24x7_20260803T171355Z --run-dir C:\Users\BalaC\phx2_paid_primary_runtime\runs\paid_primary_live_24x7_20260803T024439Z --run-dir C:\Users\BalaC\phx2_paid_primary_runtime\runs\paid_primary_live_24x7_20260802T160009Z --synthetic --out PHX2\.test_tmp\net_recovery_135x_review
```

Local evidence from this change is under
`PHX2/.test_tmp/net_recovery_135x/`: test transcripts, `comparison_final/` with
per-file SHA-256 hashes and provenance in `comparison.json`, and separate
config echoes, fills, position records, and summaries for every case/policy.
Generated ledgers and external source data are not committed.

## External config

Only Bala's `initials_recovery_multiple=1.35`, `take_profit_pct=null`, and
`runner_trailing_stop_pct=0.30` were changed in
`C:\Users\BalaC\phx2_paper_trading\paper_config.json`. Other values are preserved.
The old high-quality parameters remain present for legacy configurations but
cannot override the enabled recovery policy.

A byte-for-byte backup was retained beside it:
`paper_config.json.pre_net_recovery_135x_20261016T210243Z.bak`.
Neither external file is staged. No live process, provider request, or
message delivery was started by this change.
