import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aiognmi.client import AsyncgNMIClient


def _make_client(**cert_paths) -> AsyncgNMIClient:
    return AsyncgNMIClient(
        host="127.0.0.1",
        port=57400,
        username="user",
        password="password",
        **cert_paths,
    )


@patch("aiognmi.client.secure_channel")
@patch("aiognmi.client.ssl_channel_credentials")
def test_connect_with_all_cert_paths(
    mock_ssl_channel_credentials: MagicMock, mock_secure_channel: MagicMock, tmp_path: Path
) -> None:
    root_cert_path = tmp_path / "root.pem"
    private_key_path = tmp_path / "key.pem"
    cert_chain_path = tmp_path / "chain.pem"
    root_cert_path.write_bytes(b"root-cert-bytes")
    private_key_path.write_bytes(b"private-key-bytes")
    cert_chain_path.write_bytes(b"cert-chain-bytes")

    client = _make_client(
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
    mock_ssl_channel_credentials: MagicMock, mock_secure_channel: MagicMock, tmp_path: Path
) -> None:
    cert_chain_path = tmp_path / "chain.pem"
    cert_chain_path.write_bytes(b"cert-chain-bytes")

    client = _make_client(path_cert_chain=str(cert_chain_path))

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
    mock_ssl_channel_credentials: MagicMock, mock_secure_channel: MagicMock, tmp_path: Path
) -> None:
    missing_path = tmp_path / "missing.pem"

    client = _make_client(path_cert_chain=str(missing_path))

    with pytest.raises(FileNotFoundError):
        asyncio.run(client.connect())

    mock_ssl_channel_credentials.assert_not_called()
    mock_secure_channel.assert_not_called()
