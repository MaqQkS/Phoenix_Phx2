"""Routing config lookup and validation."""

import pytest

from PHX2.dispatch.routing import resolve_sinks, validate_routing_config


CONFIG = {
    "would_alert": {
        "CLEAN": ["file_preview", "console"],
        "PARTIAL": ["file_preview", "console"],
    },
    "skip": {"INFO": ["file_preview"]},
    "block": {"INFO": ["file_preview"]},
    "error": {"ERROR": ["file_preview", "console"]},
}


def test_resolve_returns_configured_sinks_for_known_pair():
    assert resolve_sinks(CONFIG, "would_alert", "CLEAN") == [
        "file_preview",
        "console",
    ]
    assert resolve_sinks(CONFIG, "error", "ERROR") == ["file_preview", "console"]


def test_resolve_returns_empty_for_unknown_decision_type():
    assert resolve_sinks(CONFIG, "missing_type", "CLEAN") == []


def test_resolve_returns_empty_for_unknown_severity_within_known_type():
    # would_alert has CLEAN/PARTIAL configured but not INFO.
    assert resolve_sinks(CONFIG, "would_alert", "INFO") == []


def test_resolve_returns_a_copy_so_callers_cannot_mutate_config():
    sinks = resolve_sinks(CONFIG, "would_alert", "CLEAN")
    sinks.append("evil")
    assert resolve_sinks(CONFIG, "would_alert", "CLEAN") == [
        "file_preview",
        "console",
    ]


# ---- validate_routing_config -------------------------------------------


REGISTERED = {"file_preview", "console", "discord_private_preview"}


def test_validate_accepts_valid_config():
    # No raise.
    validate_routing_config(CONFIG, REGISTERED)


def test_validate_accepts_empty_config():
    validate_routing_config({}, REGISTERED)


def test_validate_rejects_unknown_decision_type():
    config = {"WOULD_ALERT": {"CLEAN": ["file_preview"]}}
    with pytest.raises(ValueError) as excinfo:
        validate_routing_config(config, REGISTERED)
    msg = str(excinfo.value)
    assert "unknown decision_type" in msg
    assert "WOULD_ALERT" in msg


def test_validate_rejects_unknown_decision_type_arbitrary_string():
    config = {"banana": {"CLEAN": ["file_preview"]}}
    with pytest.raises(ValueError) as excinfo:
        validate_routing_config(config, REGISTERED)
    assert "banana" in str(excinfo.value)


def test_validate_rejects_lowercase_severity_casing():
    config = {"would_alert": {"clean": ["file_preview"]}}
    with pytest.raises(ValueError) as excinfo:
        validate_routing_config(config, REGISTERED)
    msg = str(excinfo.value)
    assert "unknown severity" in msg
    assert "clean" in msg


def test_validate_rejects_unknown_sink_name():
    config = {"would_alert": {"CLEAN": ["file_preview", "telegram_typo"]}}
    with pytest.raises(ValueError) as excinfo:
        validate_routing_config(config, REGISTERED)
    msg = str(excinfo.value)
    assert "unknown sink" in msg
    assert "telegram_typo" in msg


def test_validate_collects_multiple_errors():
    config = {
        "WOULD_ALERT": {"CLEAN": ["file_preview"]},  # bad casing on decision_type
        "would_alert": {
            "clean": ["file_preview"],  # bad casing on severity
            "CLEAN": ["bogus_sink"],  # bad sink
        },
    }
    with pytest.raises(ValueError) as excinfo:
        validate_routing_config(config, REGISTERED)
    msg = str(excinfo.value)
    assert "WOULD_ALERT" in msg
    assert "clean" in msg
    assert "bogus_sink" in msg


def test_validate_rejects_severity_map_that_is_not_a_dict():
    config = {"would_alert": ["file_preview"]}  # list, not dict
    with pytest.raises(ValueError) as excinfo:
        validate_routing_config(config, REGISTERED)
    msg = str(excinfo.value)
    assert "must be dict" in msg


def test_validate_rejects_sink_list_that_is_not_a_list():
    config = {"would_alert": {"CLEAN": "file_preview"}}  # str, not list
    with pytest.raises(ValueError) as excinfo:
        validate_routing_config(config, REGISTERED)
    msg = str(excinfo.value)
    assert "must be list" in msg
