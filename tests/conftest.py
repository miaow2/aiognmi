from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from grpc.aio import EOF

from aiognmi import AsyncgNMIClient
from aiognmi.proto.gnmi.gnmi_pb2 import GetResponse, SetResponse, SubscribeRequest, SubscribeResponse


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


class FakeSubscribeCall:
    """
    A scriptable fake bidirectional call standing in for the stub's `Subscribe` call object

    Records requests passed to `write()`, and replays a caller-supplied sequence of
    `SubscribeResponse` messages (or exceptions to raise) from `read()`, then `grpc.aio.EOF`.
    """

    def __init__(
        self, responses: list[SubscribeResponse | BaseException] | None = None, write_error: BaseException | None = None
    ) -> None:
        self.responses = list(responses or [])
        self.written: list[SubscribeRequest] = []
        self.cancelled = False
        self.done_writing_called = False
        self._index = 0
        self.write_error = write_error

    async def write(self, request: SubscribeRequest) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.written.append(request)

    async def read(self) -> SubscribeResponse | object:
        if self._index >= len(self.responses):
            return EOF

        item = self.responses[self._index]
        self._index += 1
        if isinstance(item, BaseException):
            raise item

        return item

    async def done_writing(self) -> None:
        self.done_writing_called = True

    def cancel(self) -> bool:
        self.cancelled = True
        return True

    def __aiter__(self) -> "FakeSubscribeCall":
        return self

    async def __anext__(self) -> SubscribeResponse:
        response = await self.read()
        if response is EOF:
            raise StopAsyncIteration

        return response


@pytest.fixture
def make_subscribe_client(
    make_client: Callable[..., AsyncgNMIClient],
) -> Callable[..., tuple[AsyncgNMIClient, FakeSubscribeCall]]:
    def _make_subscribe_client(
        responses: list[SubscribeResponse | BaseException] | None = None,
        write_error: BaseException | None = None,
    ) -> tuple[AsyncgNMIClient, FakeSubscribeCall]:
        client = make_client(insecure=True)
        client.stub = MagicMock()
        call = FakeSubscribeCall(responses, write_error=write_error)
        client.stub.Subscribe = MagicMock(return_value=call)
        return client, call

    return _make_subscribe_client
