"""Stage 23 module-local exception hierarchy (foundation only at 23.1).

Stage 23 mirrors the Stage 21 / Stage 22 module-local exception
discipline: module-local exception types rooted at plain
``Exception``, NOT at a central PHX2 error registry. Closed-set
error codes are deliberately NOT introduced in 23.1 -- the
surface is contract-only and class-level discrimination is
sufficient.

The hierarchy:

    Stage23Error(Exception)
    ├── Stage23ContractError
    ├── Stage23InputError
    ├── Stage23ManifestError
    └── Stage23BoundaryError

Each subclass is raised by a specific Stage 23 contract surface:

  * ``Stage23ContractError``  -- model construction / hash
    derivation contract violations (e.g. ``Stage23FilterResult``
    built with a label outside ``LABELS``).
  * ``Stage23InputError``     -- input-reader contract
    violations (malformed JSONL, missing file, directory where
    a file was expected, secret-leak on an input row).
  * ``Stage23ManifestError``  -- manifest builder / serializer
    contract violations (e.g. attempt to leak a secret into a
    manifest field).
  * ``Stage23BoundaryError``  -- reserved for future
    cross-stage boundary violations detected at runtime (not
    raised in 23.1; reserved for forward compatibility).

Stage 23.1 itself raises ``Stage23ContractError``,
``Stage23InputError``, and ``Stage23ManifestError``.
``Stage23BoundaryError`` is reserved for future sub-stages.
"""

from __future__ import annotations


class Stage23Error(Exception):
    """Base type for every Stage 23 surface-level violation.

    Module-local; intentionally not a subclass of any central
    PHX2 error registry so the Stage 21 / Stage 22 closed code
    registries stay out of Stage 23's surface.
    """


class Stage23ContractError(Stage23Error):
    """Raised when a Stage 23 model / hash helper sees a contract violation.

    Active in Stage 23.1. The model constructors and hash
    helpers raise this exception when:

      * a ``label`` value is not a member of ``LABELS``.
      * a ``data_status`` value is not a member of
        ``DATA_STATUSES``.
      * a ``filter_family`` value is not a member of
        ``FILTER_FAMILIES``.
      * a required string field is the empty string when the
        surface requires it non-empty.
      * a deterministic-hash helper receives an unsupported
        value type that cannot be encoded into canonical JSON.

    The detail string is a short non-secret label naming the
    offending field; raw caller-supplied content never reaches
    this surface.
    """


class Stage23InputError(Stage23Error):
    """Raised when the Stage 23 input reader sees a contract violation.

    Active in Stage 23.1. The input reader raises this exception
    when:

      * the operator-supplied path does not exist.
      * the operator-supplied path is a directory where a file
        was expected.
      * a JSONL line does not parse as a JSON object (mapping).
      * a JSONL line is not a top-level mapping (e.g. a JSON
        array, scalar, or null).
      * an input row carries a forbidden field-name substring
        (secret-bearing).
      * an input row carries a forbidden value substring (URL /
        webhook host / long-token leak shape).

    Stage 23.1 ships a strict-by-default reader: secret-leak
    detection raises rather than redacts. The detail string is
    a short non-secret label naming the failure mode; raw
    caller-supplied content never reaches this surface.
    """


class Stage23ManifestError(Stage23Error):
    """Raised when a Stage 23 manifest builder / serializer sees a contract violation.

    Active in Stage 23.1. The manifest builder raises this
    exception when:

      * a required manifest field is missing or empty.
      * a manifest field would carry a secret-bearing identifier
        (path leaks an env-var name, etc.).
      * a deterministic serializer is invoked with an
        unsupported value type.
      * the redaction-confirmation field is not the locked
        token.
    """


class Stage23BoundaryError(Stage23Error):
    """Reserved for future Stage 23 cross-stage boundary violations.

    Not raised by any Stage 23.1 surface. Locked here so future
    sub-stages can extend the cross-stage runtime guard set
    (e.g. an offline-runner that observes a forbidden Stage 21
    import attempt) without churning the public error surface.
    """


__all__ = [
    "Stage23BoundaryError",
    "Stage23ContractError",
    "Stage23Error",
    "Stage23InputError",
    "Stage23ManifestError",
]
