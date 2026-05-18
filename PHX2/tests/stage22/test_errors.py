"""Stage 22.1 error hierarchy tests.

Pins the Stage 22 exception hierarchy:

  * Every Stage 22 error class subclasses ``Stage22ContractError``.
  * ``Stage22ContractError`` subclasses ``Exception`` directly.
  * No Stage 22 error class subclasses ``Stage21Error`` -- the
    Stage 21 closed E2100/W2100 code registry stays out of Stage
    22's surface.
  * Each subclass can be raised and caught both as itself and as
    ``Stage22ContractError``.

Stage 22.1 does NOT introduce closed-set error codes. Class
discrimination is the only matching surface in 22.1.
"""

from __future__ import annotations

import pytest

from PHX2.stage21.errors import Stage21Error
from PHX2.stage22.errors import (
    Stage22CaptureContractError,
    Stage22ClassifierContractError,
    Stage22ContractError,
    Stage22LedgerContractError,
    Stage22RetryContractError,
    Stage22RunnerContractError,
)


_STAGE22_SUBCLASSES: tuple[type[Stage22ContractError], ...] = (
    Stage22LedgerContractError,
    Stage22CaptureContractError,
    Stage22ClassifierContractError,
    Stage22RetryContractError,
    Stage22RunnerContractError,
)


def test_stage22_contract_error_subclasses_exception():
    assert issubclass(Stage22ContractError, Exception)


def test_stage22_contract_error_is_not_a_stage21_error_subclass():
    assert not issubclass(Stage22ContractError, Stage21Error)


def test_every_stage22_subclass_inherits_from_stage22_contract_error():
    for cls in _STAGE22_SUBCLASSES:
        assert issubclass(cls, Stage22ContractError), (
            f"{cls.__name__} does not subclass Stage22ContractError"
        )


def test_no_stage22_subclass_inherits_from_stage21_error():
    for cls in _STAGE22_SUBCLASSES + (Stage22ContractError,):
        assert not issubclass(cls, Stage21Error), (
            f"{cls.__name__} unexpectedly subclasses Stage21Error"
        )


def test_each_stage22_subclass_round_trips_through_raise_and_catch():
    for cls in _STAGE22_SUBCLASSES:
        # Catch as itself.
        with pytest.raises(cls):
            raise cls("test detail")
        # Catch as Stage22ContractError.
        with pytest.raises(Stage22ContractError):
            raise cls("test detail")
        # Catch as plain Exception.
        with pytest.raises(Exception):
            raise cls("test detail")


def test_stage22_contract_error_accepts_short_detail_string():
    err = Stage22ContractError("short non-secret label")
    assert isinstance(err, Exception)
    # Default Exception str behaviour: args[0] becomes str(err).
    assert "short non-secret label" in str(err)


def test_each_subclass_has_a_distinct_class_object():
    classes = (Stage22ContractError,) + _STAGE22_SUBCLASSES
    assert len(set(classes)) == len(classes), (
        "Stage 22 error subclasses must each be distinct types"
    )
