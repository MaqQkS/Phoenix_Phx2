import hashlib
from types import SimpleNamespace

import pytest

from PHX2.scripts.phx2_live_paper_trade import build_parser, main, paper_transport


def args(**changes):
    base = dict(enable_paper_telegram=False, max_paper_messages=0,
                confirm_paper_destination=None, paper_destination_sha256=None)
    return SimpleNamespace(**dict(base, **changes))


def test_default_delivery_does_not_read_credentials():
    class Unreadable(dict):
        def get(self, *args):
            pytest.fail("unarmed delivery must not read any credentials")
    assert paper_transport(args(), Unreadable()) is None


@pytest.mark.parametrize("changes", [dict(max_paper_messages=1),
    dict(enable_paper_telegram=True, max_paper_messages=1),
    dict(enable_paper_telegram=True, max_paper_messages=0,
         confirm_paper_destination="PHX2_PAPER_CANARY")])
def test_partial_arming_refused(changes):
    with pytest.raises(ValueError):
        paper_transport(args(**changes), {})


def test_paper_destination_must_match_and_uses_separate_credentials(monkeypatch):
    from PHX2.delivery import telegram_transport as module
    seen = []
    monkeypatch.setattr(module, "TelegramTransport", lambda config, **kw: seen.append((config, kw)))
    chat = "-1000000012345"
    config = {"PHX2_PAPER_TELEGRAM_CHAT_ID": chat,
              "PHX2_PAPER_TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz"}
    armed = args(enable_paper_telegram=True, max_paper_messages=2,
                 confirm_paper_destination="PHX2_PAPER_CANARY",
                 paper_destination_sha256=hashlib.sha256(chat.encode()).hexdigest())
    paper_transport(armed, config)
    assert seen[0][0].chat_id == chat and seen[0][1]["max_retries"] == 0
    assert not seen[0][0].coin_images_enabled
    config["PHX2_PAPER_TELEGRAM_CHAT_ID"] = "-1000000099999"
    with pytest.raises(ValueError, match="DESTINATION_CONFIRMATION"):
        paper_transport(armed, config)
    assert len(seen) == 1


def test_live_cli_refuses_unbounded_run_before_config_read(tmp_path):
    assert main(["--inputs", str(tmp_path), "--config", str(tmp_path / "absent.json")]) == 2


def test_live_cli_rejects_phx1_and_unsafe_run_id(tmp_path):
    assert main(["--once", "--inputs", "C:/Users/BalaC/Downloads/Phoenix_Bot/data"]) == 2
    assert main(["--once", "--inputs", str(tmp_path), "--run-id", "../escape"]) == 2


def test_documented_producer_only_flag_parses():
    parsed = build_parser().parse_args(["--inputs", "synthetic", "--producer-streams-only"])
    assert parsed.producer_streams_only and not parsed.enable_paper_telegram
