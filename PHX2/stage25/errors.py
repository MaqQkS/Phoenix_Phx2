"""Stage 25 module-local exception hierarchy (foundation only at 25.1).

Stage 25 mirrors the prior-stage module-local exception
discipline: module-local exception types rooted at plain
``Exception``, NOT at a central PHX2 error registry. Closed-set
error codes are deliberately NOT introduced in 25.1 -- the
surface is contract-only and class-level discrimination is
sufficient.

The hierarchy:

    Stage25Error(Exception)
    ├── Stage25ContractError
    ├── Stage25InputError
    ├── Stage25ManifestError
    └── Stage25BoundaryError

Each subclass is raised by a specific Stage 25 contract surface:

  * ``Stage25ContractError`` -- model construction / hash
    derivation contract violations (e.g. a record built with a
    closed-set token outside the closed set).
  * ``Stage25InputError``    -- input-reader contract violations
    (malformed JSONL, missing file, directory where a file was
    expected, secret-leak on an input row, unknown input_kind).
  * ``Stage25ManifestError`` -- manifest builder / serializer
    contract violations (e.g. attempt to leak a secret into a
    manifest field, manifest basename carrying a path separator).
  * ``Stage25BoundaryError`` -- reserved for future cross-stage
    boundary violations detected at runtime (not raised in 25.1;
    reserved for forward compatibility).

Stage 25.1 itself raises ``Stage25ContractError``,
``Stage25InputError``, and ``Stage25ManifestError``.
``Stage25BoundaryError`` is reserved for future sub-stages.
"""

from __future__ import annotations


class Stage25Error(Exception):
    """Base type for every Stage 25 surface-level violation.

    Module-local; intentionally not a subclass of any central
    PHX2 error registry so the prior-stage closed code registries
    stay out of Stage 25's surface.
    """


class Stage25ContractError(Stage25Error):
    """Raised when a Stage 25 model / hash helper sees a contract violation.

    Active in Stage 25.1. The model constructors and hash helpers
    raise this exception when:

      * a closed-set token (``measurement_family`` /
        ``source_family`` / ``source_status`` /
        ``measurement_status`` / ``confidence_level`` /
        ``window_kind`` / ``candidate_kind`` /
        ``reconciliation_status`` / ``quote_denomination``) is
        not a member of its closed set.
      * a required string field is the empty string when the
        surface requires it non-empty.
      * a price / amount field is a negative integer when the
        surface requires a non-negative integer or ``None``.
      * a price field is ``0`` and the row's ``reason_codes``
        tuple does not carry the explicit observed-zero marker.
      * a price field is ``None`` and the row's source_status is
        ``PRESENT`` (``None`` is reserved for non-PRESENT statuses).
      * a deterministic-hash helper receives an unsupported value
        type that cannot be encoded into canonical JSON.

    The detail string is a short non-secret label naming the
    offending field; raw caller-supplied content never reaches
    this surface.
    """


class Stage25InputError(Stage25Error):
    """Raised when the Stage 25 input reader sees a contract violation.

    Active in Stage 25.1. The input reader raises this exception
    when:

      * the operator-supplied path does not exist.
      * the operator-supplied path is a directory where a file
        was expected.
      * the operator-supplied ``input_kind`` is not a member of
        ``INPUT_KINDS``.
      * the operator-supplied ``schema_version`` is not the
        locked Stage 25 schema version.
      * a JSONL line does not parse as a JSON object (mapping).
      * a JSONL line is not a top-level mapping (e.g. a JSON
        array, scalar, or null).
      * an intra-file blank line is observed (trailing blank
        lines are ignored).
      * an input row carries a forbidden field-name substring
        (secret-bearing) at any nesting level.
      * an input row carries a forbidden value substring (URL /
        webhook host / long-hex credential shape) at any nesting
        level.

    Stage 25.1 ships a strict-by-default reader: secret-leak
    detection raises rather than redacts. The detail string is
    a short non-secret label naming the failure mode; raw
    caller-supplied content never reaches this surface.
    """


class Stage25ManifestError(Stage25Error):
    """Raised when a Stage 25 manifest builder / serializer sees a
    contract violation.

    Active in Stage 25.1. The manifest builder raises this
    exception when:

      * a required manifest field is missing or empty.
      * a manifest file basename carries a secret-bearing or
        URL-shape substring.
      * a manifest file basename contains a path separator
        (manifests carry basenames, not paths).
      * a deterministic serializer is invoked with an
        unsupported value type.
      * the redaction-confirmation field is not the locked
        Stage 25 confirmation token or the empty string.
      * an optional Stage 24 manifest pin is supplied with one
        of (basename, sha256) but not the other.
    """


class Stage25BoundaryError(Stage25Error):
    """Reserved for future Stage 25 cross-stage boundary violations.

    Not raised by any Stage 25.1 surface. Locked here so future
    sub-stages can extend the cross-stage runtime guard set (e.g.
    a runner that observes a forbidden Stage 21 / 22 / 23 / 24
    import attempt) without churning the public error surface.
    """


__all__ = [
    "Stage25BoundaryError",
    "Stage25ContractError",
    "Stage25Error",
    "Stage25InputError",
    "Stage25ManifestError",
]
