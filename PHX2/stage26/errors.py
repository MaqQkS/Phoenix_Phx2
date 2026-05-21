"""Stage 26.1 typed errors.

Every error raised by Stage 26.1 production code is a subclass of
``Stage26Error`` and carries a closed-set ``error_code`` token from
``PHX2.stage26.constants.STAGE26_ERROR_CODES``. The error-code prefix
``STG26_CAL_`` reflects Stage 26.1's calibration-input-contract
scope; future Stage 26.x sub-stages may introduce additional code
families with their own prefixes.

Error hierarchy:

  * ``Stage26Error``                -- base; all Stage 26 errors
                                       inherit from this.
  * ``Stage26ManifestError``        -- manifest cannot be opened /
                                       parsed / validated structurally
                                       (e.g. self-entry sentinel
                                       missing).
  * ``Stage26ReaderError``          -- per-artifact read / byte-level
                                       verification failed (file
                                       missing, sha256 mismatch, byte
                                       count mismatch, row count
                                       mismatch).
  * ``Stage26SchemaError``          -- artifact JSON / JSONL row
                                       shape did not match the locked
                                       Stage 25 schema, OR carried an
                                       unknown closed-set value, OR
                                       carried an unexpected extra
                                       field.
  * ``Stage26ValidationError``      -- one or more per-artifact
                                       validations failed; carries
                                       the structured validation
                                       report so callers can inspect
                                       every failure.
  * ``Stage26EligibilityError``     -- Stage 26.2 classifier was
                                       handed a non-string truth
                                       class, or a string that is
                                       not a member of the locked
                                       Stage 26.1
                                       ``MEASUREMENT_TRUTH_CLASSES``
                                       closed set.

Stage 26.1 errors NEVER carry any of the following: a network URL,
a webhook host literal, an environment-variable name, a secret-
bearing field, a denominator-status token, or an approval-state
token. The error string formats deliberately stick to plain
diagnostic prose plus the offending artifact basename / record-
index / field-name so a Stage 26.2+ caller can react to the typed
error without parsing free-form text.
"""

from __future__ import annotations


class Stage26Error(Exception):
    """Base class for every Stage 26 typed error.

    Carries a closed-set ``error_code`` token. Stage 26.1 codes use
    the ``STG26_CAL_`` prefix; future sub-stages may declare their
    own code families. The base class accepts the code as a keyword-
    only argument so subclasses can supply a fixed default while
    callers stay explicit.
    """

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        if not isinstance(error_code, str) or error_code == "":
            raise ValueError(
                "Stage26Error error_code must be a non-empty string"
            )
        self.error_code: str = error_code


class Stage26ManifestError(Stage26Error):
    """Raised when the Stage 25 manifest cannot be opened / parsed /
    validated structurally.
    """


class Stage26ReaderError(Stage26Error):
    """Raised when a per-artifact read / byte-level verification fails.

    Distinct from ``Stage26SchemaError``: a ``Stage26ReaderError``
    indicates the file is missing, the bytes do not match the
    manifest's recorded ``sha256`` / ``byte_count``, or the JSONL
    non-blank line count does not match the manifest's recorded
    ``row_count``. A ``Stage26SchemaError`` is raised when the bytes
    parse but the resulting record shape / closed-set values are
    invalid.
    """


class Stage26SchemaError(Stage26Error):
    """Raised when an artifact row / summary / manifest carries an
    invalid shape, an unknown closed-set value, or an unexpected
    extra field.
    """


class Stage26ValidationError(Stage26Error):
    """Raised when one or more per-artifact validations failed.

    Carries the structured validation report so the caller can
    inspect every failure without re-running the validation pass.
    The ``report`` attribute is the same
    ``ArtifactValidationReport`` instance that
    ``validate_stage25_artifact_set`` returned -- not a freshly
    constructed surrogate.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        report: object,
    ) -> None:
        super().__init__(message, error_code=error_code)
        self.report: object = report


class Stage26EligibilityError(Stage26Error):
    """Raised by the Stage 26.2 classifier on an unknown truth class.

    The classifier accepts only members of the locked Stage 26.1
    ``MEASUREMENT_TRUTH_CLASSES`` tuple. Any other string (or a
    non-string) raises this error with code
    ``STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS``. The error
    deliberately does NOT label the row as a failure outcome -- the
    classifier is a pure projector, not a row validator.
    """


__all__ = [
    "Stage26EligibilityError",
    "Stage26Error",
    "Stage26ManifestError",
    "Stage26ReaderError",
    "Stage26SchemaError",
    "Stage26ValidationError",
]
