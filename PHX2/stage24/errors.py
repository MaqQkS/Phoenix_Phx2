"""Stage 24 module-local exception hierarchy (foundation only at 24.1).

Stage 24 mirrors the Stage 21 / Stage 22 / Stage 23 module-local
exception discipline: module-local exception types rooted at
plain ``Exception``, NOT at a central PHX2 error registry.
Closed-set error codes are deliberately NOT introduced in 24.1
-- the surface is contract-only and class-level discrimination
is sufficient.

The hierarchy:

    Stage24Error(Exception)
    ├── Stage24ContractError
    ├── Stage24InputError
    ├── Stage24ManifestError
    ├── Stage24BoundaryError
    └── Stage24DecoderError

Each subclass is raised by a specific Stage 24 contract surface:

  * ``Stage24ContractError`` -- model construction / hash
    derivation contract violations (e.g. a result built with a
    decoder_status outside ``DECODER_STATUSES``).
  * ``Stage24InputError``    -- input-reader contract violations
    (malformed JSONL, missing file, directory where a file was
    expected, secret-leak on an input row, unknown input_kind).
  * ``Stage24ManifestError`` -- manifest builder / serializer
    contract violations (e.g. attempt to leak a secret into a
    manifest field).
  * ``Stage24BoundaryError`` -- reserved for future cross-stage
    boundary violations detected at runtime (not raised in 24.1;
    reserved for forward compatibility).
  * ``Stage24DecoderError``  -- reserved for the Stage 24.2 /
    24.3 / 24.4 / 24.5 decoder modules. Not raised in 24.1; the
    decoder Protocol surface in
    ``PHX2/stage24/decoder_contracts.py`` ships only the
    contract.

Stage 24.1 itself raises ``Stage24ContractError``,
``Stage24InputError``, and ``Stage24ManifestError``.
``Stage24BoundaryError`` and ``Stage24DecoderError`` are
reserved for future sub-stages.
"""

from __future__ import annotations


class Stage24Error(Exception):
    """Base type for every Stage 24 surface-level violation.

    Module-local; intentionally not a subclass of any central
    PHX2 error registry so the Stage 21 / Stage 22 / Stage 23
    closed code registries stay out of Stage 24's surface.
    """


class Stage24ContractError(Stage24Error):
    """Raised when a Stage 24 model / hash helper sees a contract violation.

    Active in Stage 24.1. The model constructors and hash
    helpers raise this exception when:

      * a closed-set token (``primitive_family`` / ``decoder_status``
        / ``data_status`` / ``confidence_level`` / ``fee_source``
        / ``route_family`` / ``instruction_location``) is not a
        member of its closed set.
      * a required string field is the empty string when the
        surface requires it non-empty.
      * an amount field is a negative integer when the surface
        requires a non-negative integer or ``None``.
      * a deterministic-hash helper receives an unsupported
        value type that cannot be encoded into canonical JSON.

    The detail string is a short non-secret label naming the
    offending field; raw caller-supplied content never reaches
    this surface.
    """


class Stage24InputError(Stage24Error):
    """Raised when the Stage 24 input reader sees a contract violation.

    Active in Stage 24.1. The input reader raises this exception
    when:

      * the operator-supplied path does not exist.
      * the operator-supplied path is a directory where a file
        was expected.
      * the operator-supplied ``input_kind`` is not a member of
        ``INPUT_KINDS``.
      * a JSONL line does not parse as a JSON object (mapping).
      * a JSONL line is not a top-level mapping (e.g. a JSON
        array, scalar, or null).
      * an input row carries a forbidden field-name substring
        (secret-bearing).
      * an input row carries a forbidden value substring (URL /
        webhook host / long-hex credential shape).

    Stage 24.1 ships a strict-by-default reader: secret-leak
    detection raises rather than redacts. The detail string is
    a short non-secret label naming the failure mode; raw
    caller-supplied content never reaches this surface.
    """


class Stage24ManifestError(Stage24Error):
    """Raised when a Stage 24 manifest builder / serializer sees a contract violation.

    Active in Stage 24.1. The manifest builder raises this
    exception when:

      * a required manifest field is missing or empty.
      * a manifest file basename carries a secret-bearing or
        URL-shape substring.
      * a manifest file basename contains a path separator
        (manifests carry basenames, not paths).
      * a deterministic serializer is invoked with an
        unsupported value type.
      * the redaction-confirmation field is not the locked
        Stage 24 confirmation token or the empty string.
    """


class Stage24BoundaryError(Stage24Error):
    """Reserved for future Stage 24 cross-stage boundary violations.

    Not raised by any Stage 24.1 surface. Locked here so future
    sub-stages can extend the cross-stage runtime guard set
    (e.g. an offline-runner that observes a forbidden Stage 21
    / Stage 22 / Stage 23 import attempt) without churning the
    public error surface.
    """


class Stage24DecoderError(Stage24Error):
    """Reserved for future Stage 24 decoder contract violations.

    Not raised by any Stage 24.1 surface. The Stage 24.2 /
    24.3 / 24.4 / 24.5 decoder modules will raise this when
    they encounter an internal contract violation (a fixture
    that does not match the documented layout, a decoder that
    cannot produce a closed-set decoder_status from its inputs).
    """


__all__ = [
    "Stage24BoundaryError",
    "Stage24ContractError",
    "Stage24DecoderError",
    "Stage24Error",
    "Stage24InputError",
    "Stage24ManifestError",
]
