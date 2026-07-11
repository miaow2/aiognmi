import asyncio
import datetime
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from aiognmi import AsyncgNMIClient


def _generate_self_signed_cert(common_name: str, san_dns: str | None = None) -> bytes:
    """
    Generate a self-signed certificate PEM for use in tests

    Args:
        common_name: subject/issuer common name to embed in the certificate
        san_dns: optional DNS name to embed in the SubjectAlternativeName extension

    Returns:
        bytes: PEM-encoded certificate
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
    )
    if san_dns:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(san_dns)]), critical=False)

    cert = builder.sign(key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.PEM)


@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_with_all_cert_paths(
    mock_ssl_channel_credentials: MagicMock,
    mock_secure_channel: MagicMock,
    tmp_path: Path,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    root_cert_path = tmp_path / "root.pem"
    private_key_path = tmp_path / "key.pem"
    cert_chain_path = tmp_path / "chain.pem"
    root_cert_path.write_bytes(b"root-cert-bytes")
    private_key_path.write_bytes(b"private-key-bytes")
    cert_chain_path.write_bytes(b"cert-chain-bytes")

    client = make_client(
        path_root_cert=str(root_cert_path),
        path_private_key=str(private_key_path),
        path_cert_chain=str(cert_chain_path),
    )

    asyncio.run(client.connect())

    mock_ssl_channel_credentials.assert_called_once_with(
        root_certificates=b"root-cert-bytes",
        private_key=b"private-key-bytes",
        certificate_chain=b"cert-chain-bytes",
    )
    mock_secure_channel.assert_called_once()


@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_with_cert_chain_only(
    mock_ssl_channel_credentials: MagicMock,
    mock_secure_channel: MagicMock,
    tmp_path: Path,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    cert_chain_path = tmp_path / "chain.pem"
    cert_chain_path.write_bytes(b"cert-chain-bytes")

    client = make_client(path_cert_chain=str(cert_chain_path))

    asyncio.run(client.connect())

    mock_ssl_channel_credentials.assert_called_once_with(
        root_certificates=None,
        private_key=None,
        certificate_chain=b"cert-chain-bytes",
    )
    mock_secure_channel.assert_called_once()


@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_with_missing_cert_file_raises(
    mock_ssl_channel_credentials: MagicMock,
    mock_secure_channel: MagicMock,
    tmp_path: Path,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    missing_path = tmp_path / "missing.pem"

    client = make_client(path_cert_chain=str(missing_path))

    with pytest.raises(FileNotFoundError):
        asyncio.run(client.connect())

    mock_ssl_channel_credentials.assert_not_called()
    mock_secure_channel.assert_not_called()


@patch("aiognmi.client.ssl.get_server_certificate")
@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_verify_true_without_cert_paths_does_not_fetch(
    mock_ssl_channel_credentials: MagicMock,
    mock_secure_channel: MagicMock,
    mock_get_server_certificate: MagicMock,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    client = make_client(verify=True)

    asyncio.run(client.connect())

    mock_ssl_channel_credentials.assert_called_once_with(
        root_certificates=None,
        private_key=None,
        certificate_chain=None,
    )
    mock_secure_channel.assert_called_once()
    mock_get_server_certificate.assert_not_called()


@patch("aiognmi.client.ssl.get_server_certificate")
@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_verify_false_without_cert_paths_fetches_and_overrides_hostname(
    mock_ssl_channel_credentials: MagicMock,
    mock_secure_channel: MagicMock,
    mock_get_server_certificate: MagicMock,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    cert_pem = _generate_self_signed_cert("router-cn.example.com", san_dns="router.example.com")
    mock_get_server_certificate.return_value = cert_pem.decode("utf-8")

    client = make_client(verify=False)

    asyncio.run(client.connect())

    mock_get_server_certificate.assert_called_once_with(("127.0.0.1", 57400))
    mock_ssl_channel_credentials.assert_called_once_with(
        root_certificates=cert_pem,
        private_key=None,
        certificate_chain=None,
    )
    mock_secure_channel.assert_called_once()
    options = mock_secure_channel.call_args.kwargs["options"]
    assert ("grpc.ssl_target_name_override", "router.example.com") in options
    assert ("grpc.default_authority", "router.example.com") in options


@patch("aiognmi.client.ssl.get_server_certificate")
@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_verify_false_falls_back_to_common_name(
    mock_ssl_channel_credentials: MagicMock,
    mock_secure_channel: MagicMock,
    mock_get_server_certificate: MagicMock,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    cert_pem = _generate_self_signed_cert("router-cn.example.com")
    mock_get_server_certificate.return_value = cert_pem.decode("utf-8")

    client = make_client(verify=False)

    asyncio.run(client.connect())

    options = mock_secure_channel.call_args.kwargs["options"]
    assert ("grpc.ssl_target_name_override", "router-cn.example.com") in options
    assert ("grpc.default_authority", "router-cn.example.com") in options


@patch("aiognmi.client.ssl.get_server_certificate")
@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_verify_false_logs_warning(
    mock_ssl_channel_credentials: MagicMock,
    mock_secure_channel: MagicMock,
    mock_get_server_certificate: MagicMock,
    caplog: pytest.LogCaptureFixture,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    cert_pem = _generate_self_signed_cert("router.example.com", san_dns="router.example.com")
    mock_get_server_certificate.return_value = cert_pem.decode("utf-8")

    client = make_client(verify=False)

    with caplog.at_level("WARNING"):
        asyncio.run(client.connect())

    assert any(record.levelname == "WARNING" and "disabled" in record.message.lower() for record in caplog.records)


@patch("aiognmi.client.ssl.get_server_certificate")
@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_verify_false_with_root_cert_path_keeps_file_bytes(
    mock_ssl_channel_credentials: MagicMock,
    mock_secure_channel: MagicMock,
    mock_get_server_certificate: MagicMock,
    tmp_path: Path,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    root_cert_path = tmp_path / "root.pem"
    root_cert_path.write_bytes(b"root-cert-bytes")

    cert_pem = _generate_self_signed_cert("router-cn.example.com", san_dns="router.example.com")
    mock_get_server_certificate.return_value = cert_pem.decode("utf-8")

    client = make_client(verify=False, path_root_cert=str(root_cert_path))

    asyncio.run(client.connect())

    mock_ssl_channel_credentials.assert_called_once_with(
        root_certificates=b"root-cert-bytes",
        private_key=None,
        certificate_chain=None,
    )
    options = mock_secure_channel.call_args.kwargs["options"]
    assert ("grpc.ssl_target_name_override", "router.example.com") in options
    assert ("grpc.default_authority", "router.example.com") in options


@patch("aiognmi.client.ssl.get_server_certificate")
@patch("aiognmi.client.ssl_channel_credentials")
@patch("aiognmi.client.insecure_channel")
def test_connect_insecure_with_verify_false_skips_tls(
    mock_insecure_channel: MagicMock,
    mock_ssl_channel_credentials: MagicMock,
    mock_get_server_certificate: MagicMock,
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    client = make_client(insecure=True, verify=False)

    asyncio.run(client.connect())

    mock_insecure_channel.assert_called_once()
    mock_ssl_channel_credentials.assert_not_called()
    mock_get_server_certificate.assert_not_called()
