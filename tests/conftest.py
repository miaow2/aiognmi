from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiognmi import AsyncgNMIClient
from aiognmi.proto.gnmi.gnmi_pb2 import GetResponse, SetResponse


@pytest.fixture
def make_client() -> Callable[..., AsyncgNMIClient]:
    def _make_client(**kwargs: Any) -> AsyncgNMIClient:
        return AsyncgNMIClient(
            host="127.0.0.1",
            port=57400,
            username="user",
            password="password",
            **kwargs,
        )

    return _make_client


@pytest.fixture
def client_with_mock_get(make_client: Callable[..., AsyncgNMIClient]) -> AsyncgNMIClient:
    client = make_client(insecure=True)
    client.stub = MagicMock()
    client.stub.Get = AsyncMock(return_value=GetResponse())
    return client


@pytest.fixture
def client_with_mock_set(make_client: Callable[..., AsyncgNMIClient]) -> AsyncgNMIClient:
    client = make_client(insecure=True)
    client.stub = MagicMock()
    client.stub.Set = AsyncMock(return_value=SetResponse())
    return client
