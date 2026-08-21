"""Serve one minimal HTTPS request over HTTP/3 for the generated Demo."""

import asyncio
import datetime
import ipaddress
import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Set

try:
    from aioquic.asyncio import QuicConnectionProtocol, serve
    from aioquic.h3.connection import H3_ALPN, H3Connection
    from aioquic.h3.events import DataReceived, HeadersReceived
    from aioquic.quic.configuration import QuicConfiguration
    from aioquic.quic.events import ProtocolNegotiated, QuicEvent
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
except ImportError as exc:
    raise ImportError(
        "Missing QUIC Demo dependency. Please install: "
        "aioquic>=1.0,<1.3 on Python 3.9, or aioquic>=1.3,<2 on Python 3.10+"
    ) from exc


class DemoHttp3Protocol(QuicConnectionProtocol):
    """Return a finite JSON response for each completed HTTP/3 request."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize protocol state before HTTP/3 negotiation completes."""
        super().__init__(*args, **kwargs)
        self._http: Optional[H3Connection] = None
        self._responded: Set[int] = set()

    def quic_event_received(self, event: QuicEvent) -> None:
        """Translate negotiated QUIC events into minimal HTTP/3 responses."""
        if isinstance(event, ProtocolNegotiated):
            self._http = H3Connection(self._quic)
        if self._http is None:
            return
        for http_event in self._http.handle_event(event):
            if isinstance(http_event, HeadersReceived) and http_event.stream_ended:
                self._respond(http_event.stream_id)
            elif isinstance(http_event, DataReceived) and http_event.stream_ended:
                self._respond(http_event.stream_id)

    def _respond(self, stream_id: int) -> None:
        """Send exactly one bounded JSON response on the request stream."""
        if stream_id in self._responded or self._http is None:
            return
        self._responded.add(stream_id)
        body = json.dumps(
            {"protocol": "HTTP/3", "experimental": True},
            separators=(",", ":"),
        ).encode("utf-8")
        self._http.send_headers(
            stream_id=stream_id,
            headers=[
                (b":status", b"200"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        )
        self._http.send_data(stream_id=stream_id, data=body, end_stream=True)
        self.transmit()


def _write_certificate(directory: Path) -> tuple:
    """Create an ephemeral localhost certificate for this Demo process."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path = directory / "certificate.pem"
    key_path = directory / "private-key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return certificate_path, key_path


async def main() -> None:
    """Bind one UDP server and remain alive until an external shutdown signal."""
    port = int(os.environ.get("SCRAPY_CFFI_DEMO_QUIC_PORT", "18443"))
    with tempfile.TemporaryDirectory(prefix="scrapy-cffi-quic-") as temp_dir:
        certificate_path, key_path = _write_certificate(Path(temp_dir))
        configuration = QuicConfiguration(
            alpn_protocols=H3_ALPN,
            is_client=False,
        )
        configuration.load_cert_chain(str(certificate_path), str(key_path))
        await serve(
            "127.0.0.1",
            port,
            configuration=configuration,
            create_protocol=DemoHttp3Protocol,
        )
        print(
            "HTTP/3 demo server started on https://127.0.0.1:%s" % port,
            flush=True,
        )
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
