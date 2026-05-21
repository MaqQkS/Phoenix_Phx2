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
  * ``Stage26CohortError``          -- Stage 26.3 cohort builder
                                       rejected its inputs: an
                                       unknown cohort dimension
                                       token, an empty / malformed
                                       dimensions tuple, a row whose
                                       Stage 25 manifest hash does
                                       not match the bundle's pin,
                                       an invalid cohort-key shape,
                                       or a row carrying a Stage 26
                                       closed-set status outside
                                       the locked vocabulary.
  * ``Stage26ThresholdError``       -- Stage 26.4 threshold candidate
                                       generator rejected its inputs
                                       or detected an invariant
                                       violation in its outputs.
                                       Carries one of the
                                       ``STG26_CAL_THRESHOLD_*`` code
                                       tokens declared in
                                       ``PHX2.stage26.threshold_constants``.
  * ``Stage26PolicyCandidateError`` -- Stage 26.5 observe-only policy
                                       candidate builder / writer
                                       rejected its inputs or
                                       detected a safety-lock
                                       violation. Carries one of the
                                       ``STG26_CAL_POLICY_CANDIDATE_*``
                                       code tokens declared in
                                       ``PHX2.stage26.policy_candidate_constants``.

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


class Stage26CohortError(Stage26Error):
    """Raised by the Stage 26.3 cohort builder on invalid inputs.

    The error wraps one of the Stage 26.3 cohort-error code tokens
    (``STG26_CAL_COHORT_*`` in ``PHX2.stage26.cohort_constants``):

      * ``STG26_CAL_COHORT_UNKNOWN_DIMENSION`` -- the caller supplied
        a dimensions tuple containing a token outside the locked
        ``COHORT_DIMENSIONS`` closed set.
      * ``STG26_CAL_COHORT_EMPTY_INPUT`` -- the caller supplied an
        empty dimensions tuple. Stage 26.3 requires at least one
        explicit dimension because cohorts decide nothing implicit.
      * ``STG26_CAL_COHORT_MIXED_MANIFEST_HASH`` -- the input
        eligibility rows carry more than one Stage 25 manifest hash,
        OR a row's hash disagrees with the eligibility bundle pin.
      * ``STG26_CAL_COHORT_INVALID_KEY`` -- a cohort key was
        constructed with mismatched ``dimensions`` / ``values``
        lengths.
      * ``STG26_CAL_COHORT_UNSUPPORTED_STATUS`` -- a row carried a
        Stage 26 closed-set status token outside the locked
        vocabulary (defensive check; Stage 26.2 output should never
        produce this).

    The error deliberately does NOT label any non-``MEASURED`` truth
    class as a failure -- Stage 26.3 preserves Stage 26.2's truth-
    class semantics verbatim and treats every Stage 25 truth class
    as a first-class category.
    """


class Stage26ThresholdError(Stage26Error):
    """Raised by the Stage 26.4 threshold candidate generator.

    The error wraps one of the Stage 26.4 typed-error code tokens
    declared in ``PHX2.stage26.threshold_constants``:

      * ``STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND`` -- the caller
        supplied a candidate-kind token outside the locked
        ``THRESHOLD_CANDIDATE_KINDS`` closed set.
      * ``STG26_CAL_THRESHOLD_INVALID_DIRECTION`` -- a candidate
        carried a direction token outside the locked
        ``THRESHOLD_DIRECTIONS`` closed set (defensive; the generator
        should never produce this).
      * ``STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS`` -- a cohort
        summary carried a ``cohort_status`` outside the locked
        Stage 26.3 ``COHORT_STATUSES`` closed set.
      * ``STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH`` -- the input
        cohort summaries carry more than one Stage 25 manifest hash,
        OR a summary's hash disagrees with the cohort-result pin.
      * ``STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY`` -- a cohort
        summary's ``primary_measured_denominator_count`` exceeds its
        ``measured_count``, which would imply a non-``MEASURED`` row
        was upgraded into the primary measured denominator (Stage
        26.4 forbids the upgrade).
      * ``STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE`` -- a cohort
        summary's truth-class / denominator-status counts do not sum
        to ``row_count``, OR a count is negative.
      * ``STG26_CAL_THRESHOLD_POLICY_LEAK`` -- a generated candidate
        ended up with ``operator_approved=True`` or
        ``runtime_consumable=True``. Stage 26.4 candidates are
        ALWAYS candidate-only and never runtime-consumable; the
        check is a defensive invariant.

    The error deliberately does NOT label any non-``MEASURED`` truth
    class as a failure -- Stage 26.4 preserves Stage 26.2's truth-
    class semantics verbatim and treats every Stage 25 truth class
    as a first-class category.
    """


class Stage26PolicyCandidateError(Stage26Error):
    """Raised by the Stage 26.5 observe-only policy candidate
    builder / writer.

    The error wraps one of the Stage 26.5 typed-error code tokens
    declared in ``PHX2.stage26.policy_candidate_constants``:

      * ``STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD`` -- the
        builder received a Stage 26.4 candidate carrying a status /
        readiness / kind / direction token outside its locked
        Stage 26.4 closed set.
      * ``STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK`` -- an emitted
        Stage 26.5 candidate ended up with ``candidate_only`` flipped
        to False, or with any other safety-lock invariant violated
        beyond the dedicated approval / runtime sub-codes below.
      * ``STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK`` -- an emitted
        candidate ended up with ``operator_approved=True``. Stage
        26.5 candidates are NEVER operator-approved; the check is a
        defensive invariant against a future refactor.
      * ``STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK`` -- an emitted
        candidate ended up with ``runtime_consumable=True`` or
        ``enforcement_enabled=True``. Stage 26.5 candidates are
        NEVER runtime-consumable and NEVER enforcement-enabled.
      * ``STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS`` -- the builder
        produced (or was asked to produce) a candidate with a
        ``candidate_status`` outside the locked
        ``POLICY_CANDIDATE_STATUSES`` closed set.
      * ``STG26_CAL_POLICY_CANDIDATE_HASH_MISMATCH`` -- the writer
        recomputed an artifact's sha256 / byte_count / row_count and
        the manifest entry does not match.
      * ``STG26_CAL_POLICY_CANDIDATE_MANIFEST_INVALID`` -- the
        manifest body the writer assembled is structurally invalid
        (e.g. missing self-entry sentinel, missing required artifact
        entry).
      * ``STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED`` -- the
        writer's redaction sweep over the row / summary / manifest
        bytes detected a forbidden substring (a URL fragment, a
        webhook host, a secret-shaped token, an approval-leak
        marker).
      * ``STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID`` -- the
        caller-supplied output directory does not exist or is not a
        directory; the writer refuses to create arbitrary parent
        directories.
      * ``STG26_CAL_POLICY_CANDIDATE_RUNTIME_FILENAME_LEAK`` -- the
        writer was asked (or attempted) to emit an artifact under a
        runtime-policy basename. Stage 26.5 writers ONLY emit the
        locked observe-only basenames.
      * ``STG26_CAL_POLICY_CANDIDATE_MIXED_MANIFEST_HASH`` -- the
        Stage 26.4 input set carries policy candidates whose
        ``stage25_manifest_hash`` disagrees with the set's pin.
      * ``STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS`` -- a
        Stage 26.4 candidate carried an ``evidence_class`` token
        outside the locked Stage 26.4
        ``THRESHOLD_EVIDENCE_CLASSES`` closed set; Stage 26.5 refuses
        to invent a fallback policy-candidate kind.

    The error deliberately does NOT label any non-``MEASURED`` truth
    class as a failure -- Stage 26.5 preserves Stage 26.2 / 26.3 /
    26.4 truth-class semantics verbatim and treats every Stage 25
    truth class as a first-class category.
    """


__all__ = [
    "Stage26CohortError",
    "Stage26EligibilityError",
    "Stage26Error",
    "Stage26ManifestError",
    "Stage26PolicyCandidateError",
    "Stage26ReaderError",
    "Stage26SchemaError",
    "Stage26ThresholdError",
    "Stage26ValidationError",
]
