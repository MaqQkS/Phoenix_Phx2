"""Bounded HTTPS transport for Telegram Bot API ``sendMessage``."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import http.client
import json
import socket
import threading
import time
import uuid
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlencode

from .telegram_config import TelegramConfig
from .telegram_composer import TELEGRAM_INTERNAL_MAX_CHARACTERS, rendered_character_count
from .telegram_media import MAX_BANNER_BYTES, PHOTO_CAPTION_LIMIT, prepare_logo_banner


SENT_OK = "SENT_OK"
RATE_LIMITED = "RATE_LIMITED"
AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
CHAT_NOT_FOUND = "CHAT_NOT_FOUND"
BOT_NOT_ALLOWED = "BOT_NOT_ALLOWED"
MESSAGE_REJECTED = "MESSAGE_REJECTED"
MESSAGE_TOO_LONG = "MESSAGE_TOO_LONG"
NETWORK_ERROR = "NETWORK_ERROR"
TIMEOUT = "TIMEOUT"
MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
UNKNOWN_FAILURE = "UNKNOWN_FAILURE"
CLOSED = "TRANSPORT_CLOSED"

TELEGRAM_RESULTS = frozenset((
    SENT_OK,
    RATE_LIMITED,
    AUTHENTICATION_FAILED,
    CHAT_NOT_FOUND,
    BOT_NOT_ALLOWED,
    MESSAGE_REJECTED,
    MESSAGE_TOO_LONG,
    NETWORK_ERROR,
    TIMEOUT,
    MALFORMED_RESPONSE,
    UNKNOWN_FAILURE,
    CLOSED,
))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class TelegramTransportResult:
    ok: bool
    transport_status: str
    message_id: Optional[int]
    destination_alias: str
    attempted_at_utc: str
    delivered_at_utc: Optional[str]
    retry_count: int
    safe_error_category: Optional[str]
    send_attempt_count: int
    presentation_mode: str = "TEXT"
    media_status: Optional[str] = None

    def evidence(self) -> dict[str, Any]:
        evidence = {
            "transport": "TELEGRAM",
            "message_id": self.message_id,
            "destination_alias": self.destination_alias,
            "attempted_at_utc": self.attempted_at_utc,
            "delivered_at_utc": self.delivered_at_utc,
            "result": self.transport_status,
            "retry_count": self.retry_count,
            "safe_error_category": self.safe_error_category,
        }
        if self.media_status is not None:
            evidence.update(presentation_mode=self.presentation_mode,
                            media_status=self.media_status,
                            send_attempt_count=self.send_attempt_count)
        return evidence


class TelegramTransport:
    """One-message Telegram sender with bounded retry and no secret output."""

    def __init__(
        self,
        config: TelegramConfig,
        *,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 10.0,
        total_attempt_timeout_seconds: float = 16.0,
        max_retries: int = 2,
        retry_delay_seconds: float = 1.0,
        connection_factory: Callable[..., Any] = http.client.HTTPSConnection,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        utc_now_fn: Callable[[], str] = _utc_now,
        evidence_sink: Optional[Callable[[Mapping[str, Any]], None]] = None,
        banner_preparer: Callable[[object], tuple[Optional[bytes], str]] = prepare_logo_banner,
    ) -> None:
        if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0:
            raise ValueError("TELEGRAM_TIMEOUT_INVALID")
        if total_attempt_timeout_seconds < max(
            connect_timeout_seconds, read_timeout_seconds
        ):
            raise ValueError("TELEGRAM_TOTAL_TIMEOUT_INVALID")
        if isinstance(max_retries, bool) or not 0 <= int(max_retries) <= 5:
            raise ValueError("TELEGRAM_RETRY_COUNT_INVALID")
        if retry_delay_seconds < 0 or retry_delay_seconds > 30:
            raise ValueError("TELEGRAM_RETRY_DELAY_INVALID")
        self._config = config
        self._connect_timeout = float(connect_timeout_seconds)
        self._read_timeout = float(read_timeout_seconds)
        self._total_timeout = float(total_attempt_timeout_seconds)
        self._max_retries = int(max_retries)
        self._retry_delay = float(retry_delay_seconds)
        self._connection_factory = connection_factory
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._utc_now = utc_now_fn
        self._evidence_sink = evidence_sink
        self._banner_preparer = banner_preparer
        self._lock = threading.Lock()
        self._closed = False

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def _result(
        self,
        *,
        result: str,
        attempted_at: str,
        attempts: int,
        message_id: Optional[int] = None,
    ) -> TelegramTransportResult:
        ok = result == SENT_OK and isinstance(message_id, int) and not isinstance(message_id, bool)
        verdict = TelegramTransportResult(
            ok=ok,
            transport_status=(SENT_OK if ok else result),
            message_id=(message_id if ok else None),
            destination_alias=self._config.destination_alias,
            attempted_at_utc=attempted_at,
            delivered_at_utc=(self._utc_now() if ok else None),
            retry_count=max(0, attempts - 1),
            safe_error_category=(None if ok else result),
            send_attempt_count=attempts,
        )
        if self._evidence_sink is not None:
            self._evidence_sink(verdict.evidence())
        return verdict

    @staticmethod
    def _classify_error(status: int, payload: Mapping[str, Any]) -> str:
        if status >= 500:
            return UNKNOWN_FAILURE  # a server failure does not prove non-delivery
        if status == 401:
            return AUTHENTICATION_FAILED
        if status == 403:
            return BOT_NOT_ALLOWED
        if status == 429 or payload.get("error_code") == 429:
            return RATE_LIMITED
        description = str(payload.get("description") or "").lower()
        if "chat not found" in description:
            return CHAT_NOT_FOUND
        if "message is too long" in description or "message too long" in description:
            return MESSAGE_TOO_LONG
        if status == 400 or payload.get("ok") is False:
            return MESSAGE_REJECTED
        return UNKNOWN_FAILURE

    def _request_once(self, text: str, photo: Optional[bytes] = None) -> tuple[str, Optional[int]]:
        connection = None
        started = self._monotonic()
        try:
            connection = self._connection_factory(
                "api.telegram.org", timeout=self._connect_timeout)
            connection.connect()
            sock = getattr(connection, "sock", None)
            if sock is not None and hasattr(sock, "settimeout"):
                sock.settimeout(self._read_timeout)
            fields = {
                "chat_id": self._config.chat_id,
                "parse_mode": self._config.parse_mode,
            }
            if photo is None:
                fields.update(text=text, link_preview_options=json.dumps(
                    {"is_disabled": True}, separators=(",", ":")))
                body = urlencode(fields).encode("utf-8")
                content_type = "application/x-www-form-urlencoded; charset=utf-8"
                method = "sendMessage"
            else:
                fields["caption"] = text
                boundary = "phx2-" + uuid.uuid4().hex
                parts = []
                for name, value in fields.items():
                    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; '
                                  f'name="{name}"\r\n\r\n{value}\r\n').encode("utf-8"))
                parts.extend([
                    (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; '
                     'filename="coin-banner.png"\r\nContent-Type: image/png\r\n\r\n').encode("ascii"),
                    photo, f"\r\n--{boundary}--\r\n".encode("ascii"),
                ])
                body = b"".join(parts)
                content_type = f"multipart/form-data; boundary={boundary}"
                method = "sendPhoto"
            connection.request(
                "POST",
                f"/bot{self._config.bot_token}/{method}",
                body=body,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(body)),
                    "User-Agent": "PHX2-Telegram/1",
                },
            )
            response = connection.getresponse()
            raw = response.read()
            if self._monotonic() - started > self._total_timeout:
                return TIMEOUT, None
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, TypeError):
                return MALFORMED_RESPONSE, None
            if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
                return MALFORMED_RESPONSE, None
            if 200 <= int(response.status) < 300 and payload.get("ok") is True:
                message = payload.get("result")
                message_id = message.get("message_id") if isinstance(message, dict) else None
                if isinstance(message_id, int) and not isinstance(message_id, bool):
                    return SENT_OK, message_id
                return MALFORMED_RESPONSE, None
            return self._classify_error(int(response.status), payload), None
        except (TimeoutError, socket.timeout):
            return TIMEOUT, None
        except (OSError, http.client.HTTPException):
            return NETWORK_ERROR, None
        except Exception:
            return UNKNOWN_FAILURE, None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def _send_body(self, text: str, photo: Optional[bytes] = None) -> TelegramTransportResult:
        attempted_at = self._utc_now()
        with self._lock:
            if self._closed:
                return self._result(
                    result=CLOSED, attempted_at=attempted_at, attempts=0)
        if not isinstance(text, str) or not text.strip():
            return self._result(
                result=MESSAGE_REJECTED, attempted_at=attempted_at, attempts=0)
        limit = PHOTO_CAPTION_LIMIT if photo is not None else TELEGRAM_INTERNAL_MAX_CHARACTERS
        if rendered_character_count(text) > limit:
            return self._result(
                result=MESSAGE_TOO_LONG, attempted_at=attempted_at, attempts=0)

        attempts = 0
        result = UNKNOWN_FAILURE
        message_id: Optional[int] = None
        while attempts <= self._max_retries:
            attempts += 1
            result, message_id = self._request_once(text, photo)
            if result == SENT_OK:
                break
            # A lost response can mean delivered. Let the durable delivery
            # journal hold it UNKNOWN; never duplicate it inside transport.
            if result != RATE_LIMITED:
                break
            if attempts <= self._max_retries:
                self._sleep(self._retry_delay)
        return self._result(
            result=result,
            attempted_at=attempted_at,
            attempts=attempts,
            message_id=message_id,
        )

    def send_html(self, text: str) -> TelegramTransportResult:
        return self._send_body(text)

    def send_alert(self, text: str, *, logo_url: object = None) -> TelegramTransportResult:
        """One logical alert: photo OR text. Never fallback on an uncertain send."""
        with self._lock:
            closed = self._closed
        if closed or not isinstance(text, str) or not text.strip():
            return self.send_html(text)
        banner = None
        reason = "IMAGE_DISABLED"
        if self._config.coin_images_enabled:
            if not isinstance(text, str) or rendered_character_count(text) > PHOTO_CAPTION_LIMIT:
                reason = "CAPTION_TOO_LONG"
            else:
                try:
                    banner, reason = self._banner_preparer(logo_url)
                except Exception:
                    reason = "IMAGE_PREPARATION_FAILED"
                if banner is not None and (not isinstance(banner, bytes)
                        or not banner.startswith(b"\x89PNG\r\n\x1a\n")
                        or len(banner) > MAX_BANNER_BYTES):
                    banner, reason = None, "BANNER_INVALID"
        if banner is None:
            return replace(self.send_html(text), media_status=reason)
        result = self._send_body(text, banner)
        if result.transport_status in (MESSAGE_REJECTED, MESSAGE_TOO_LONG):
            fallback = self.send_html(text)
            return replace(fallback, media_status="PHOTO_REJECTED_TEXT_FALLBACK",
                           send_attempt_count=result.send_attempt_count + fallback.send_attempt_count)
        return replace(result, presentation_mode="PHOTO", media_status=(
            "BANNER_SENT" if result.ok else "PHOTO_FAILED_NO_FALLBACK"))

    def send_one_audited_post(
        self, *, webhook_identity: Optional[str], payload: Mapping[str, Any]
    ) -> TelegramTransportResult:
        """Compatibility with the existing one-message guarded transport seam."""

        del webhook_identity
        if not isinstance(payload, Mapping) or set(payload.keys()) != {"content"}:
            return self._result(
                result=MESSAGE_REJECTED,
                attempted_at=self._utc_now(),
                attempts=0,
            )
        return self.send_html(payload.get("content"))  # type: ignore[arg-type]


__all__ = (
    "SENT_OK",
    "RATE_LIMITED",
    "AUTHENTICATION_FAILED",
    "CHAT_NOT_FOUND",
    "BOT_NOT_ALLOWED",
    "MESSAGE_REJECTED",
    "MESSAGE_TOO_LONG",
    "NETWORK_ERROR",
    "TIMEOUT",
    "MALFORMED_RESPONSE",
    "UNKNOWN_FAILURE",
    "TELEGRAM_RESULTS",
    "TelegramTransport",
    "TelegramTransportResult",
)
