"""Stage 21 credential attestation records and writer.

A ``CredentialAttestation`` is the manifest-safe snapshot of a
single Stage 21 secret slot: it records only the slot name, the
presence flag, the optional byte length, and the truncated sha256
fingerprint. The raw value is never stored.

Stage 21.1 ships the model and a deterministic serializer here.
A later sub-stage will write attestation files to disk as part of
the Stage 21 run manifest; 21.1 ships only the in-memory record
plus the public-summary helper.

The Stage 21 closure handoff (Section G) forbids reading any
environment variable that contains an API key or webhook URL into
the live preview path. ``CredentialAttestation`` is the
attestable, separately-scoped artifact that satisfies the
"separately scoped, attestable mechanism" clause of that rule.
"""

from __future__ import annotations

from typing import Iterable, Mapping, NamedTuple, Sequence

from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21SecretError
from PHX2.stage21.secret_redaction import SecretRef


class CredentialAttestation(NamedTuple):
    """Manifest-safe snapshot of a single Stage 21 secret slot.

    Fields:
      * ``name``: non-secret label (typically the env-var name).
      * ``present``: True iff the underlying value was non-empty.
      * ``length``: byte length of the underlying value (``0`` when
        absent).
      * ``fingerprint``: ``sha256(value).hexdigest()[:12]`` when
        present, else the empty string.

    ``CredentialAttestation`` is intentionally separate from
    ``SecretRef`` so the attestation writer's output schema can
    evolve without touching the in-memory ``SecretRef`` shape. The
    fields are identical today; the indirection is for future
    schema work.
    """

    name: str
    present: bool
    length: int
    fingerprint: str

    def public_summary(self) -> dict[str, object]:
        """Return the manifest-safe summary mapping.

        Stable key order across runs; values are non-secret.
        """
        return {
            "name": self.name,
            "present": self.present,
            "length": self.length,
            "fingerprint": self.fingerprint,
        }


def attestation_from_secret_ref(ref: SecretRef) -> CredentialAttestation:
    """Build a ``CredentialAttestation`` from a ``SecretRef``.

    The function is the only supported way to convert. It performs
    a defensive shape check and raises ``Stage21SecretError``
    (E2104) if a non-``SecretRef`` value is passed.

    Because ``SecretRef`` and ``CredentialAttestation`` share the
    same four fields today, the conversion is a direct copy.
    """
    if not isinstance(ref, SecretRef):
        raise Stage21SecretError(
            Stage21ErrorCode.E2104,
            detail=(
                "attestation_from_secret_ref expected SecretRef but got "
                f"{type(ref).__name__}"
            ),
        )
    return CredentialAttestation(
        name=ref.name,
        present=ref.present,
        length=ref.length,
        fingerprint=ref.fingerprint,
    )


def build_attestation_bundle(
    refs: Sequence[SecretRef],
) -> tuple[CredentialAttestation, ...]:
    """Convert a sequence of ``SecretRef`` into a frozen attestation tuple.

    The returned tuple is sorted lexicographically by ``name`` so
    repeated runs over the same input set produce byte-identical
    serialized output. ``Stage21SecretError`` (E2104) is raised if
    any element is not a ``SecretRef`` or if two refs share the same
    name (collisions would otherwise hide one slot from the
    manifest).
    """
    seen_names: set[str] = set()
    for ref in refs:
        if not isinstance(ref, SecretRef):
            raise Stage21SecretError(
                Stage21ErrorCode.E2104,
                detail=(
                    "build_attestation_bundle expected Iterable[SecretRef]; "
                    f"got element of type {type(ref).__name__}"
                ),
            )
        if ref.name in seen_names:
            raise Stage21SecretError(
                Stage21ErrorCode.E2104,
                detail=(
                    f"build_attestation_bundle saw duplicate slot name "
                    f"{ref.name!r}"
                ),
            )
        seen_names.add(ref.name)
    return tuple(
        sorted(
            (attestation_from_secret_ref(r) for r in refs),
            key=lambda a: a.name,
        )
    )


def serialize_attestation_bundle(
    bundle: Iterable[CredentialAttestation],
) -> list[Mapping[str, object]]:
    """Serialize an attestation bundle to a deterministic list of dicts.

    Returned as a plain ``list[dict]`` so the JSON writer in
    ``PHX2.stage21.telemetry_writers`` can serialize it directly.
    Order matches the input order; callers that need stable order
    should pre-sort with ``build_attestation_bundle`` or sort
    manually before calling this.

    Raises ``Stage21SecretError`` (E2104) if any element is not a
    ``CredentialAttestation`` instance.
    """
    out: list[Mapping[str, object]] = []
    for record in bundle:
        if not isinstance(record, CredentialAttestation):
            raise Stage21SecretError(
                Stage21ErrorCode.E2104,
                detail=(
                    "serialize_attestation_bundle expected "
                    "Iterable[CredentialAttestation]; got element of type "
                    f"{type(record).__name__}"
                ),
            )
        out.append(record.public_summary())
    return out


__all__ = [
    "CredentialAttestation",
    "attestation_from_secret_ref",
    "build_attestation_bundle",
    "serialize_attestation_bundle",
]
