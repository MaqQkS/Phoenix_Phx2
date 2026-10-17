from dataclasses import replace
import io
import socket
from types import SimpleNamespace

import pytest

from PHX2.delivery import telegram_media as media
from PHX2.delivery.telegram_composer import rendered_character_count, FIELD_UNAVAILABLE_DISPLAY
from PHX2.delivery.telegram_config import TelegramConfig, TelegramConfigError
from PHX2.delivery.telegram_presentation import compose_discovery_alert
from PHX2.delivery.telegram_transport import TelegramTransport
from PHX2.tests.delivery.test_telegram_composer import _sample
from PHX2.tests.delivery.test_telegram_config import _values
from PHX2.tests.delivery.test_telegram_delivery import _run, _snapshot, _delivery_context, MINT
from PHX2.tests.delivery.test_telegram_transport import (
    _config, FakeConnection, FakeResponse, ConnectionScript,
)

PNG = b"\x89PNG\r\n\x1a\nmock-encoded-banner"
LOGO = "https://images.example.com/token.png"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Network calls are forbidden in presentation tests")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def transport(script, *, preparer=lambda _: (PNG, "BANNER_READY"), enabled=True):
    return TelegramTransport(replace(_config(), coin_images_enabled=enabled),
                             connection_factory=script, sleep_fn=lambda _: None,
                             banner_preparer=preparer)


def success():
    return FakeConnection(FakeResponse(200, {"ok": True, "result": {"message_id": 42}}))


def test_compact_caption_preserves_truthful_state_without_research_sections():
    result = compose_discovery_alert(_sample())
    assert "Discovery alert · no paper fill implied" in result.text
    assert "MC: $10k | Post-mig ATH: $57k | Mig: $32k" in result.text
    assert "Global Fees: Pending / unavailable" in result.text
    assert f"Risk: {_sample().risk_warning}" in result.text
    assert "Coverage: Complete since migration" in result.text
    assert all(text not in result.text for text in ("Ante", "Builder Read", "Fee Gate:"))
    assert result.rendered_character_count < 1024


def test_caption_escaping_missing_fields_and_partial_coverage():
    result = compose_discovery_alert(replace(
        _sample(), token_identity="<b>bad</b> & \"name\"", market_cap="",
        risk_warning="", discovery_provenance="DEXSCREENER_RESTART_BACKFILL",
        ath_coverage="PARTIAL_SINCE_ADMISSION"))
    assert "&lt;b&gt;bad&lt;/b&gt; &amp; &quot;name&quot;" in result.text
    assert f"MC: {FIELD_UNAVAILABLE_DISPLAY}" in result.text and "Risk: Unverified" in result.text
    assert "Obs ATH" in result.text and "Post-mig ATH" not in result.text
    assert "Coverage: Partial (restart backfill)" in result.text


def test_shadow_warning_is_not_removed_to_make_caption_shorter():
    result = compose_discovery_alert(replace(
        _sample(), phx1_structural_policy_mode="SHADOW",
        original_phx1_structural_verdict="HARD_BLOCK",
        effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
        shadow_warning_reasons=("EXAMPLE_REASON",), manual_review_required=True,
        policy_reason_display="Liquidity evidence incomplete"))
    assert "SHADOW BLOCK" in result.text and "Manual review required" in result.text
    assert "organicity unverified" in result.text


def test_photo_success_has_caption_and_no_buttons_or_extra_message():
    connection = success()
    script = ConnectionScript(connection)
    result = transport(script).send_alert("<b>Discovery</b>", logo_url=LOGO)
    assert result.ok and result.presentation_mode == "PHOTO"
    assert result.media_status == "BANNER_SENT" and len(script.calls) == 1
    method, path, body, headers = connection.request_record
    assert path.endswith("/sendPhoto") and PNG in body
    assert b'name="caption"' in body and b"<b>Discovery</b>" in body
    assert b'name="parse_mode"' in body and b"reply_markup" not in body
    assert LOGO.encode() not in body and "images.example" not in repr(result.evidence())


@pytest.mark.parametrize("reason", ["IMAGE_MISSING", "IMAGE_DOWNLOAD_FAILED",
                                     "PILLOW_UNAVAILABLE", "IMAGE_DECODE_FAILED"])
def test_image_absence_or_preparation_failure_sends_text_once(reason):
    connection = success()
    script = ConnectionScript(connection)
    result = transport(script, preparer=lambda _: (None, reason)).send_alert("caption")
    assert result.ok and result.presentation_mode == "TEXT" and result.media_status == reason
    assert connection.request_record[1].endswith("/sendMessage")
    assert b"reply_markup" not in connection.request_record[2] and len(script.calls) == 1


def test_disabled_images_and_long_caption_never_prepare_or_split():
    def unexpected(_):
        pytest.fail("image preparation must not run")
    for enabled, text, status in [(False, "short", "IMAGE_DISABLED"),
                                  (True, "🔥" * 513, "CAPTION_TOO_LONG")]:
        connection = success()
        script = ConnectionScript(connection)
        result = transport(script, preparer=unexpected, enabled=enabled).send_alert(text)
        assert result.ok and result.media_status == status and len(script.calls) == 1
        assert connection.request_record[1].endswith("/sendMessage")
    assert rendered_character_count("<b>&amp;🔥</b>") == 3


def test_explicit_photo_rejection_falls_back_exactly_once():
    photo = FakeConnection(FakeResponse(400, {"ok": False, "error_code": 400}))
    text = success()
    script = ConnectionScript(photo, text)
    result = transport(script).send_alert("caption")
    assert result.ok and result.media_status == "PHOTO_REJECTED_TEXT_FALLBACK"
    assert result.send_attempt_count == 2 and len(script.calls) == 2
    assert photo.request_record[1].endswith("/sendPhoto")
    assert text.request_record[1].endswith("/sendMessage")


@pytest.mark.parametrize("response", [FakeResponse(502, {"ok": False}),
    FakeResponse(200, b"malformed"), FakeResponse(200, {"ok": True, "result": {}})])
def test_uncertain_photo_outcomes_have_no_retry_or_text_fallback(response):
    script = ConnectionScript(FakeConnection(response))
    result = transport(script).send_alert("caption")
    assert not result.ok and len(script.calls) == 1
    assert result.media_status == "PHOTO_FAILED_NO_FALLBACK"


@pytest.mark.parametrize("photo", [False, True])
def test_lost_response_never_retries(photo):
    class LostResponse(FakeConnection):
        def getresponse(self):
            raise socket.timeout()
    script = ConnectionScript(LostResponse())
    sender = transport(script)
    result = sender.send_alert("caption") if photo else sender.send_html("caption")
    assert result.transport_status == "TIMEOUT" and len(script.calls) == 1


def test_rate_limited_photo_retries_without_text_fallback():
    limited = FakeConnection(FakeResponse(429, {"ok": False, "error_code": 429}))
    accepted = success()
    script = ConnectionScript(limited, accepted)
    result = transport(script).send_alert("caption")
    assert result.ok and result.retry_count == 1
    assert all(c.request_record[1].endswith("/sendPhoto") for c in (limited, accepted))


def test_guard_duplicate_never_reaches_image_or_transport(monkeypatch):
    script = ConnectionScript()
    def unexpected(_):
        pytest.fail("duplicate must not prepare an image")
    result, _, composed, attempts = _run(
        monkeypatch, transport(script, preparer=unexpected), duplicate=True)
    assert result["send_result"] is None
    assert script.calls == [] and attempts == []


def test_real_adapter_uses_compact_photo_route_and_preserves_artifact_proofs(monkeypatch):
    script = ConnectionScript(success())
    result, adapter, composed, attempts = _run(monkeypatch, transport(script))
    assert result["send_result"].transport_ok
    assert composed[0]["alert_kind"] == "DISCOVERY_ALERT"
    assert composed[0]["inline_buttons"] is False
    assert composed[0]["source_proofs"]["central_ath_market_cap"] == "57000"
    assert attempts[0]["media_status"] == "BANNER_SENT"


@pytest.mark.parametrize("value", [None, "", "http://example.com/a.png",
    "https://localhost/a", "https://127.0.0.1/a", "https://[::1]/a",
    "https://user:password@example.com/a", "https://example.com/a?key=hidden",
    "https://example.com:8443/a", "https://example.com/a#fragment"])
def test_unsafe_or_missing_image_urls_rejected(value):
    assert media.validate_logo_url(value) is None


def resolver(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def test_download_pins_validated_public_ip_and_closes():
    records = []
    class Download(FakeConnection):
        def __init__(self, host, address, timeout):
            super().__init__()
            records.append((host, address, timeout, self))
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            stream = io.BytesIO(b"source")
            return SimpleNamespace(status=200, getheader=lambda key: "image/png" if key == "Content-Type" else "6",
                                   read=stream.read)
    data, status = media.download_logo(LOGO, resolver=resolver, connection_factory=Download)
    assert data == b"source" and status == "IMAGE_DOWNLOADED"
    assert records[0][:2] == ("images.example.com", "93.184.216.34")
    assert records[0][3].closed


def test_private_dns_answer_cannot_open_socket():
    def private(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 443))]
    data, status = media.download_logo(LOGO, resolver=private)
    assert data is None and status == "IMAGE_HOST_NOT_PUBLIC"


@pytest.mark.parametrize("status,content_type,length,expected", [
    (302, "image/png", "1", "IMAGE_HTTP_REJECTED"),
    (404, "image/png", "1", "IMAGE_HTTP_REJECTED"),
    (200, "image/svg+xml", "1", "IMAGE_CONTENT_TYPE_INVALID"),
    (200, "image/png", "5000001", "IMAGE_SIZE_INVALID"),
])
def test_download_rejects_redirects_content_type_and_oversized_images(status, content_type, length, expected):
    class Download(FakeConnection):
        def __init__(self, *args):
            super().__init__()
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return SimpleNamespace(status=status,
                getheader=lambda key: content_type if key == "Content-Type" else length,
                read=lambda *_: pytest.fail("rejected response body must not be read"))
    assert media.download_logo(LOGO, resolver=resolver, connection_factory=Download) == (None, expected)


def test_logo_rides_existing_overview_without_additional_provider_call():
    from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
    from PHX2.stage29.stage29_2_birdeye_models import BIRDEYE_REFUSAL_REASON_NONE
    calls = []
    payload = {"address": MINT, "mc": 24000, "liquidity": 18000, "logoURI": LOGO}
    def get(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            body={"data": payload}, fetched_at_utc="2026-10-16T12:00:00Z", http_status_code=200)
    client = SimpleNamespace(get=get, _secret="offline-test-only")
    result = PaidBirdeyeMarketTransport.fetch_overview_plane(client, MINT)
    assert result["token_logo_url"] == LOGO and len(calls) == 1
    payload["address"] = "different-mint"
    result = PaidBirdeyeMarketTransport.fetch_overview_plane(client, MINT)
    assert "token_logo_url" not in result and result["_market_failure_reason"] == "PROVIDER_WRONG_MINT"


def test_closed_transport_never_prepares_image():
    script = ConnectionScript()
    sender = transport(script, preparer=lambda _: pytest.fail("closed transport must not prepare"))
    sender.close()
    assert sender.send_alert("caption").transport_status == "TRANSPORT_CLOSED"
    assert script.calls == []


def test_preview_is_self_contained_and_explicitly_synthetic():
    from PHX2.scripts.phx2_preview_telegram import preview_html
    html = preview_html()
    assert "all tokens and metrics are synthetic" in html
    assert "actual 1000x200 PNG renderer requires Pillow" in html
    assert "PHOENIX PAPER \u2014 ENTRY" in html and "STAKE RECOVERED" in html
    assert "PHOENIX PAPER \u2014 FINAL EXIT" in html
    assert "<script" not in html and "src=\"http" not in html
    assert "Discovery alert · no paper fill implied" in html


def test_missing_pillow_never_downloads(monkeypatch):
    monkeypatch.setattr(media, "load_pillow", lambda: None)
    monkeypatch.setattr(media, "download_logo", lambda _: pytest.fail("must not download"))
    assert media.prepare_logo_banner(LOGO) == (None, "PILLOW_UNAVAILABLE")


def test_real_banner_dimensions_and_bad_decode_when_pillow_available():
    Image = pytest.importorskip("PIL.Image", reason="Pillow is not installed; image rendering requires separate dependency authorization")
    source = io.BytesIO()
    Image.new("RGBA", (120, 120), (20, 150, 220, 180)).save(source, format="PNG")
    banner, status = media.build_coin_banner(source.getvalue())
    assert status == "BANNER_READY"
    with Image.open(io.BytesIO(banner)) as result:
        assert result.size == (1000, 200) and result.mode == "RGB"
    assert media.build_coin_banner(b"not an image")[1] == "IMAGE_DECODE_FAILED"
    from PHX2.scripts.phx2_preview_telegram import synthetic_banner, preview_html
    rendered, status = synthetic_banner()
    assert status == "BANNER_READY"
    assert 'src="data:image/png;base64,' in preview_html(rendered)
    assert "illustrative placeholder" not in preview_html(rendered)


def test_image_setting_is_explicit_opt_in_and_strict():
    values = _values()
    assert TelegramConfig.from_mapping(values).coin_images_enabled is False
    values["PHX2_TELEGRAM_COIN_IMAGES_ENABLED"] = "true"
    assert TelegramConfig.from_mapping(values).coin_images_enabled is True
    values["PHX2_TELEGRAM_COIN_IMAGES_ENABLED"] = "maybe"
    with pytest.raises(TelegramConfigError, match="TELEGRAM_COIN_IMAGES_SETTING_MALFORMED"):
        TelegramConfig.from_mapping(values)
