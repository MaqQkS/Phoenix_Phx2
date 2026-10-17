# Clean source snapshot checkpoint

This checkpoint publishes the reviewed PHX2 source without importing the local feature branch's history. It does not deploy or activate PHX2.

## Provenance and equivalence

- Reviewed source commit: `21a90d77e44abf7625b7d00a24d930faaca0a6f7`.
- Reviewed source tree: `a01a5e74bad4b74322f83e32bbca920f5107c405`.
- Snapshot parent, verified private remote master: `aa59d19048c6dc3925f65b58264ac39e9b226dc5`.
- Clean source tree before adding this checkpoint note: `157f4b2e13ac6789a81a3e3a039b3c5458c21b4d`.
- All 1,898 retained source/test/documentation/asset/manifest files have identical Git blobs to the reviewed source. No retained source file was edited. This note is the only added file.
- Original local feature branch and its history are preserved. Remote master is not changed by this publication.

## Explicit exclusions

- `PHX2/dashboard/config.json`: actual machine-local runtime directory and ledger configuration. No values are reproduced here.
- `architect_dump_internal.md`: private operator architecture note; excluded from the snapshot tip.
- Untracked or ignored environment files, external real configs, credentials, databases, logs, caches, virtual environments and generated test/run/review evidence are not included.

Safe example configuration, required dependency/provenance manifests, three dashboard PNG assets and reduced regression fixtures remain. Non-secret path references in existing code, examples and provenance documentation remain byte-identical; they are not copies of external runtime configuration files. The reduced six-row JSONL regression fixture is intentional test data, not a runtime log bundle.

Remote master already contains the private operator note and an obsolete worktree gitlink in older history. This snapshot removes the note at its tip; it does not rewrite that existing remote ancestry or add the local feature branch's ancestry. Gitlinks are recorded as historical tree metadata, not followed as submodule contents.

## Offline validation of this isolated snapshot

- Integration scope: **509 passed in 22.93 seconds**, no skips; network guard reported zero blocked socket attempts. Scope: paper trading, delivery, paper preflight, ATH telemetry/accounting, central ATH and delivery transactions.
- Additional Helius asyncio scope: **7 passed in 0.41 seconds**, mocked provider transports, zero non-loopback attempts and 14 Windows loopback socket operations.
- The 40 presentation cases are included in the 509 integration cases; they must not be counted again. The seven Helius asyncio cases are separate from that integration scope. Earlier runs of these same scopes are repeated verification, not additional unique tests.
- Production renderer: `BANNER_READY`, synthetic 1000 x 200 RGB PNG, 31,308 bytes, Pillow 13.0.0. PNG SHA-256: `095a805233735edd56e89f4c2052dd0916a6227832d0fede33f9d258639c0d8f`. The rendered preview and logs stay local and are not included in Git.
- Rendering used modules from this isolated snapshot and a socket-blocking wrapper; zero connection attempts were observed.
- Existing whitespace warnings in four unchanged source test files were preserved for exact source equivalence; this note introduces no such warning.

## Publication inspection

The clean source tree and all 207 inherited master commits were scanned before this note was added: 2,915 unique blob/commit contents, 65,578,540 bytes. Credential-pattern matches were classified as reviewed test sentinels, placeholders or code references; no confirmed live credential and no unresolved match was found. No prohibited database/cache/environment/raw-log path was present. The final commit, including this note, is rescanned before push. No credential-validity provider calls are made.

## Deployment remains separate

Publication does not update external launchers, runtime configurations or credentials. Deployment still requires selecting the reviewed code pin and digest, exact source/output roots, exposure and pricing capacity, finite runtime/provider budgets, and separately authorized message destinations and delivery. Live activation, provider calls, Telegram sends and PHX1 changes are not part of this checkpoint.
