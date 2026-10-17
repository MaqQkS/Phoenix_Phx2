"""Optional PHX1-style logo banner. Network stays at this delivery boundary.

Only a public HTTPS logo from an existing exact-mint metadata observation is
accepted. No provider lookup, redirect, local file access, or URL logging.
Pillow is optional: a missing dependency always yields the text fallback.
"""
from __future__ import annotations

import http.client
import io
import ipaddress
import socket
import ssl
import queue
import threading
import time
import warnings
from urllib.parse import urlsplit

MAX_SOURCE_BYTES = 5_000_000
MAX_BANNER_BYTES = 1_000_000
MAX_DIMENSION = 4096
MAX_PIXELS = 12_000_000
BANNER_SIZE = (1000, 200)
PHOTO_CAPTION_LIMIT = 1024
_DNS_SLOTS = threading.BoundedSemaphore(2)


def _resolve_bounded(resolver, host: str, timeout: float):
    """Bound DNS wall time and concurrent abandoned resolver calls."""
    if not _DNS_SLOTS.acquire(blocking=False):
        raise TimeoutError()
    results = queue.Queue(maxsize=1)
    def resolve():
        try:
            results.put((True, resolver(host, 443, type=socket.SOCK_STREAM)))
        except Exception:
            results.put((False, None))
        finally:
            _DNS_SLOTS.release()
    threading.Thread(target=resolve, daemon=True).start()
    ok, value = results.get(timeout=max(0.001, timeout))
    if not ok:
        raise OSError()
    return value


def validate_logo_url(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if (parts.scheme != "https" or not host or parts.username or parts.password
                or parts.port not in (None, 443) or parts.query or parts.fragment):
            return None
        if host.lower() == "localhost" or host.lower().endswith((".local", ".localhost")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            host.encode("ascii")
        return value
    except (ValueError, UnicodeError):
        return None


def load_pillow():
    try:
        from PIL import Image, ImageFilter, ImageOps
        return Image, ImageFilter, ImageOps
    except (ImportError, OSError):
        return None


def build_coin_banner(source: bytes, *, pillow=None) -> tuple[bytes | None, str]:
    if not isinstance(source, bytes) or not 0 < len(source) <= MAX_SOURCE_BYTES:
        return None, "IMAGE_SIZE_INVALID"
    pillow = pillow or load_pillow()
    if pillow is None:
        return None, "PILLOW_UNAVAILABLE"
    Image, ImageFilter, ImageOps = pillow
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(source)) as probe:
                w, h = probe.size
                if (not 0 < w <= MAX_DIMENSION or not 0 < h <= MAX_DIMENSION
                        or w * h > MAX_PIXELS or probe.format not in ("PNG", "JPEG", "WEBP")):
                    return None, "IMAGE_FORMAT_OR_DIMENSIONS_INVALID"
                probe.verify()
            with Image.open(io.BytesIO(source)) as decoded:
                decoded.load()
                source_image = ImageOps.exif_transpose(decoded).convert("RGBA")
        logo = source_image.copy()
        logo.thumbnail((170, 170), Image.Resampling.LANCZOS)
        background = ImageOps.fit(source_image, BANNER_SIZE,
                                  method=Image.Resampling.LANCZOS).filter(
                                      ImageFilter.GaussianBlur(radius=24))
        banner = Image.new("RGBA", BANNER_SIZE, (11, 20, 26, 255))
        banner.alpha_composite(background)
        banner.alpha_composite(Image.new("RGBA", BANNER_SIZE, (0, 0, 0, 140)))
        banner.alpha_composite(logo, ((1000 - logo.width) // 2, (200 - logo.height) // 2))
        output = io.BytesIO()
        banner.convert("RGB").save(output, format="PNG", optimize=True, compress_level=9)
        content = output.getvalue()
        if len(content) > MAX_BANNER_BYTES:
            return None, "BANNER_SIZE_INVALID"
        return content, "BANNER_READY"
    except Exception:
        return None, "IMAGE_DECODE_FAILED"


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        raw = socket.create_connection((self._address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def download_logo(url: str, *, resolver=None,
                  connection_factory=_PinnedHTTPSConnection,
                  clock=time.monotonic) -> tuple[bytes | None, str]:
    valid = validate_logo_url(url)
    if valid is None:
        return None, "IMAGE_URL_INVALID"
    connection = None
    deadline = clock() + 3.0
    try:
        parts = urlsplit(valid)
        addresses = {item[4][0] for item in _resolve_bounded(
            resolver or socket.getaddrinfo, parts.hostname, deadline - clock())}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            return None, "IMAGE_HOST_NOT_PUBLIC"
        if clock() >= deadline:
            return None, "IMAGE_TIMEOUT"
        connection = connection_factory(parts.hostname, sorted(addresses)[0], deadline - clock())
        connection.request("GET", parts.path or "/", headers={"Accept": "image/png,image/jpeg,image/webp"})
        response = connection.getresponse()
        if response.status != 200:
            return None, "IMAGE_HTTP_REJECTED"  # redirects never followed
        content_type = (response.getheader("Content-Type") or "").split(";")[0].lower()
        if content_type not in ("image/png", "image/jpeg", "image/webp"):
            return None, "IMAGE_CONTENT_TYPE_INVALID"
        length = response.getheader("Content-Length")
        if length and int(length) > MAX_SOURCE_BYTES:
            return None, "IMAGE_SIZE_INVALID"
        chunks = bytearray()
        while len(chunks) <= MAX_SOURCE_BYTES:
            remaining = deadline - clock()
            if remaining <= 0:
                return None, "IMAGE_TIMEOUT"
            sock = getattr(connection, "sock", None)
            if sock is not None:
                sock.settimeout(remaining)
            chunk = response.read(min(65536, MAX_SOURCE_BYTES + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        if not chunks or len(chunks) > MAX_SOURCE_BYTES:
            return None, "IMAGE_SIZE_INVALID"
        return bytes(chunks), "IMAGE_DOWNLOADED"
    except Exception:
        return None, "IMAGE_DOWNLOAD_FAILED"
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def prepare_logo_banner(url: object) -> tuple[bytes | None, str]:
    if url is None:
        return None, "IMAGE_MISSING"
    valid = validate_logo_url(url)
    if valid is None:
        return None, "IMAGE_URL_INVALID"
    pillow = load_pillow()
    if pillow is None:
        return None, "PILLOW_UNAVAILABLE"  # do not download something we cannot decode
    content, reason = download_logo(valid)
    if content is None:
        return None, reason
    return build_coin_banner(content, pillow=pillow)
