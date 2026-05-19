"""Stage 22 module-local exception hierarchy (foundation only at 22.1).

Stage 22 mirrors the Stage 21.3A / 21.3B / 21.3C / 21.4 pattern:
module-local exception types rooted at plain ``Exception``,
NOT at the central ``Stage21Error`` registry. Closed-set error
codes are deliberately NOT introduced in 22.1 -- the surface is
contract-only and class-level discrimination is sufficient.

If Stage 22.2+ runtime modules need code-level discrimination
(e.g. a downstream consumer matching on ``.code`` rather than
on exception type), codes can land additively then. Stage 22.1
does not pre-emptively introduce them because no consumer of
22.1 contracts needs them.

The hierarchy:

    Stage22ContractError(Exception)
    ├── Stage22LedgerContractError
    ├── Stage22CaptureContractError
    ├── Stage22ClassifierContractError
    ├── Stage22RetryContractError
    ├── Stage22RunnerContractError
    ├── Stage22BatchHandlingContractError
    └── Stage22RunnerError

Each subclass is raised by a specific Stage 22 contract surface
on a hard contract violation (e.g. ``classify_failure`` called
with an out-of-set ``status_class`` value). Stage 22.1 itself
raises only ``Stage22ClassifierContractError``; Stage 22.4
additionally raises ``Stage22BatchHandlingContractError`` from
the pure ``handle_provider_batch`` helper for input-coherence
violations. Stage 22.5 introduces ``Stage22RunnerError`` for
runner-level argument / config / composition violations
detected at the bounded private ingest runner boundary, plus
the live composition private-ping body builder. The remaining
subclasses (``Stage22LedgerContractError``,
``Stage22CaptureContractError``, ``Stage22RetryContractError``,
``Stage22RunnerContractError``) remain reserved for downstream
ledger / capture writer / retry policy / future runner-contract
surfaces.
"""

from __future__ import annotations


class Stage22ContractError(Exception):
    """Base type for every Stage 22 contract-level violation.

    Module-local; intentionally not a subclass of
    ``PHX2.stage21.errors.Stage21Error`` so the Stage 21 closed
    E2100/W2100 code registry stays out of Stage 22's surface.
    Stage 22.1 does NOT activate Stage 21's reserved ``E2140`` /
    ``E2141`` ledger codes; future Stage 22 sub-stages may
    introduce their own codes if required, but this hierarchy is
    code-free in 22.1.
    """


class Stage22LedgerContractError(Stage22ContractError):
    """Raised when a ``DedupeLedger`` implementation violates the contract.

    Stage 22.1 ships the ``DedupeLedger`` Protocol only; this
    exception is reserved for the future ledger implementation
    (Stage 22.2+) when it detects an invariant violation -- e.g.
    ``mark_dispatched`` called for an unknown key, malformed
    ledger record, or a corrupt persistence layer state.

    The ``ledger_unavailable`` outcome of ``check_and_record``
    is NOT an exception path: transient ledger storage failures
    surface via the ``DedupeOutcome`` outcome token. This
    exception type is reserved for hard contract violations
    only.
    """


class Stage22CaptureContractError(Stage22ContractError):
    """Raised when a ``RawCaptureWriter`` implementation violates the contract.

    Stage 22.1 ships the ``RawCaptureWriter`` Protocol only; this
    exception is reserved for the future capture writer
    implementation (Stage 22.2+) when it detects an invariant
    violation -- e.g. record shape mismatch, capture target path
    invalid, durability assertion failure.
    """


class Stage22ClassifierContractError(Stage22ContractError):
    """Raised when ``classify_failure`` receives a contract-violating input.

    Active in Stage 22.1. The classifier raises this exception
    when:

      * ``outcome.ok is True`` (failure-classifying a successful
        outcome is incoherent), or
      * ``status_class`` is not a member of
        ``STATUS_CLASSES``, or
      * ``upstream_error_type`` is not a member of
        ``UPSTREAM_ERROR_TYPES``.

    The detail string is a short non-secret label naming the
    offending field; raw exception material from the upstream
    adapter never reaches this surface.
    """


class Stage22RetryContractError(Stage22ContractError):
    """Raised when a retry-policy implementation violates the contract.

    Stage 22.1 ships only the ``RetryCap`` / ``RetryDecision``
    record shapes and the ``RETRY_DECISIONS`` closed token set;
    no policy is implemented. This exception is reserved for the
    future retry policy (Stage 22.2+) when it would emit a
    decision outside ``RETRY_DECISIONS`` or a cap shape outside
    ``RetryCap``'s invariants (e.g. ``max_attempts < 1``).
    """


class Stage22RunnerContractError(Stage22ContractError):
    """Raised when bounded-runner construction violates the contract.

    Stage 22.1 ships no runner; this exception is reserved for
    the future Stage 22 bounded runner (Stage 22.5+) at
    construction-time argument validation -- analogous to the
    Stage 21.4 ``Stage21RunnerError`` but in the Stage 22
    ingest-runner context. NOT raised in Stage 22.4.
    """


class Stage22BatchHandlingContractError(Stage22ContractError):
    """Raised when the Stage 22.4 pure batch helper receives an
    incoherent input or an injected callable returns an out-of-
    contract value.

    Active in Stage 22.4. The ``handle_provider_batch`` helper
    raises this exception when:

      * ``fetch_outcome.ok`` is False but ``fetch_outcome.responses``
        is non-empty (a failed fetch cannot also carry events).
      * ``fetch_outcome.ok`` is True but ``fetch_outcome.status_class``
        is not ``"success"``.
      * ``decode_event_fn`` returns a value that is not a
        ``NormalizedLiveEvent``.
      * A successfully decoded event's ``chain`` does not match the
        caller-supplied chain (provenance mismatch).
      * ``classify_decode_error_fn`` returns a value outside
        ``MALFORMED_EVENT_REASONS``.
      * The malformed raw payload cannot satisfy the safe
        ``MalformedEventRecord`` builder contract for any field
        other than the fields the helper itself derives.

    The detail string is a short non-secret label. Raw exception
    material, raw payload values, and provider-supplied URLs /
    headers / API keys NEVER reach this surface.
    """


class Stage22RunnerError(Stage22ContractError):
    """Raised by the Stage 22.5 bounded private ingest runner and its
    live composition helpers on runner-level argument / config /
    composition violations.

    Active in Stage 22.5. The bounded runner raises this
    exception when:

      * ``max_provider_attempts`` is not the locked value ``1`` in
        22.5 (retry execution is deferred to Stage 22.6).
      * ``max_events`` is provided and is not a strict positive
        int (``bool`` rejected; ``<= 0`` rejected).
      * ``max_dispatches`` is provided and is not a strict
        positive int (``bool`` rejected; ``<= 0`` rejected).
      * ``provider_id`` / ``chain`` are not non-empty strings.
      * Any required keyword-only collaborator is missing or
        ``None``.
      * The live composition private-ping body builder produces
        a body that exceeds the locked length cap or that
        contains a forbidden URL / secret-bearing substring.

    The detail string is a short non-secret label. Raw exception
    material, raw payload values, and provider-supplied URLs /
    headers / API keys NEVER reach this surface. This type
    deliberately mirrors the Stage 21 runner-style error pattern
    (``Stage21RunnerError``) at the Stage 22 bounded-runner
    boundary; the older ``Stage22RunnerContractError`` remains
    reserved for runner-contract construction surfaces and is
    NOT raised by the Stage 22.5 runner.
    """


__all__ = [
    "Stage22BatchHandlingContractError",
    "Stage22CaptureContractError",
    "Stage22ClassifierContractError",
    "Stage22ContractError",
    "Stage22LedgerContractError",
    "Stage22RetryContractError",
    "Stage22RunnerContractError",
    "Stage22RunnerError",
]
