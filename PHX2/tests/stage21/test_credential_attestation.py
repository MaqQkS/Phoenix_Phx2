"""Stage 21 credential_attestation tests."""

from __future__ import annotations

import pytest

from PHX2.stage21.credential_attestation import (
    CredentialAttestation,
    attestation_from_secret_ref,
    build_attestation_bundle,
    serialize_attestation_bundle,
)
from PHX2.stage21.errors import Stage21SecretError
from PHX2.stage21.secret_redaction import SecretRef, build_secret_ref


SAMPLE_SECRET = "phx2-stage21-test-fake-secret-A1B2C3D4"


def test_attestation_carries_only_public_fields():
    ref = build_secret_ref("PHX2_STAGE21_PROVIDER_API_KEY", SAMPLE_SECRET)
    attestation = attestation_from_secret_ref(ref)
    assert attestation.name == "PHX2_STAGE21_PROVIDER_API_KEY"
    assert attestation.present is True
    assert attestation.length == len(SAMPLE_SECRET.encode("utf-8"))
    assert attestation.fingerprint == ref.fingerprint


def test_attestation_records_missing_slot():
    ref = build_secret_ref("EMPTY", None)
    attestation = attestation_from_secret_ref(ref)
    assert attestation.present is False
    assert attestation.length == 0
    assert attestation.fingerprint == ""


def test_attestation_repr_does_not_include_secret_value():
    ref = build_secret_ref("X", SAMPLE_SECRET)
    attestation = attestation_from_secret_ref(ref)
    assert SAMPLE_SECRET not in repr(attestation)
    assert SAMPLE_SECRET not in str(attestation)


def test_attestation_from_invalid_input_raises():
    with pytest.raises(Stage21SecretError) as excinfo:
        attestation_from_secret_ref("not-a-secret-ref")  # type: ignore[arg-type]
    assert excinfo.value.code == "E2104"


def test_build_attestation_bundle_is_sorted_by_name():
    refs = [
        build_secret_ref("BBB", SAMPLE_SECRET),
        build_secret_ref("AAA", None),
        build_secret_ref("CCC", SAMPLE_SECRET + "-x"),
    ]
    bundle = build_attestation_bundle(refs)
    assert [a.name for a in bundle] == ["AAA", "BBB", "CCC"]
    # Each entry is the attestation form.
    for a in bundle:
        assert isinstance(a, CredentialAttestation)


def test_build_attestation_bundle_rejects_duplicate_names():
    refs = [
        build_secret_ref("DUPE", SAMPLE_SECRET),
        build_secret_ref("DUPE", "another"),
    ]
    with pytest.raises(Stage21SecretError) as excinfo:
        build_attestation_bundle(refs)
    assert excinfo.value.code == "E2104"


def test_build_attestation_bundle_rejects_non_secret_ref_element():
    with pytest.raises(Stage21SecretError) as excinfo:
        build_attestation_bundle([build_secret_ref("X", "v"), "bad"])  # type: ignore[list-item]
    assert excinfo.value.code == "E2104"


def test_serialize_attestation_bundle_returns_list_of_public_dicts():
    refs = [
        build_secret_ref("AAA", SAMPLE_SECRET),
        build_secret_ref("BBB", None),
    ]
    bundle = build_attestation_bundle(refs)
    serialized = serialize_attestation_bundle(bundle)
    assert isinstance(serialized, list)
    assert all(isinstance(d, dict) for d in serialized)
    for d in serialized:
        assert set(d.keys()) == {"name", "present", "length", "fingerprint"}


def test_serialize_attestation_bundle_rejects_bad_element():
    with pytest.raises(Stage21SecretError):
        serialize_attestation_bundle(["bad"])  # type: ignore[list-item]


def test_serialize_output_has_no_raw_secret_in_any_string_value():
    refs = [
        build_secret_ref("API_KEY", SAMPLE_SECRET),
    ]
    bundle = build_attestation_bundle(refs)
    serialized = serialize_attestation_bundle(bundle)
    for d in serialized:
        for value in d.values():
            if isinstance(value, str):
                assert SAMPLE_SECRET not in value
