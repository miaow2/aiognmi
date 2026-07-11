import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

from aiognmi import AsyncgNMIClient, Extension, ExtensionID, RegisteredExtension
from aiognmi.proto.gnmi.gnmi_pb2 import GetRequest, GetResponse, SetRequest, SetResponse


def _make_extension(payload: bytes = b"payload") -> Extension:
    return Extension(
        registered_ext=RegisteredExtension(id=ExtensionID.Value("EID_EXPERIMENTAL"), msg=payload),
    )


def test_get_request_includes_extensions(make_client: Callable[..., AsyncgNMIClient]) -> None:
    client = make_client(insecure=True)
    client.stub = MagicMock()
    extension = _make_extension()
    client.stub.Get = AsyncMock(return_value=GetResponse())

    asyncio.run(client.get(paths=["/interfaces/interface[name=Management0]"], extensions=[extension]))

    request = client.stub.Get.call_args.args[0]
    assert isinstance(request, GetRequest)
    assert list(request.extension) == [extension]


def test_get_request_defaults_to_empty_extensions(make_client: Callable[..., AsyncgNMIClient]) -> None:
    client = make_client(insecure=True)
    client.stub = MagicMock()
    client.stub.Get = AsyncMock(return_value=GetResponse())

    asyncio.run(client.get(paths=["/interfaces/interface[name=Management0]"]))

    request = client.stub.Get.call_args.args[0]
    assert isinstance(request, GetRequest)
    assert list(request.extension) == []


def test_set_request_includes_extensions(make_client: Callable[..., AsyncgNMIClient]) -> None:
    client = make_client(insecure=True)
    client.stub = MagicMock()
    extension = _make_extension()
    client.stub.Set = AsyncMock(return_value=SetResponse())

    asyncio.run(
        client.set(
            update=[
                {"path": "/interfaces/interface[name=Management0]/config", "data": {"description": "gnmi update test"}},
            ],
            extensions=[extension],
        )
    )

    request = client.stub.Set.call_args.args[0]
    assert isinstance(request, SetRequest)
    assert list(request.extension) == [extension]


def test_set_union_replace_request_includes_extensions(make_client: Callable[..., AsyncgNMIClient]) -> None:
    client = make_client(insecure=True)
    client.stub = MagicMock()
    extension = _make_extension()
    client.stub.Set = AsyncMock(return_value=SetResponse())

    asyncio.run(
        client.set(
            union_replace=[
                {"path": "/interfaces/interface[name=Management0]/config", "data": {"description": "gnmi update test"}},
            ],
            extensions=[extension],
        )
    )

    request = client.stub.Set.call_args.args[0]
    assert isinstance(request, SetRequest)
    assert list(request.extension) == [extension]


def test_set_request_defaults_to_empty_extensions(make_client: Callable[..., AsyncgNMIClient]) -> None:
    client = make_client(insecure=True)
    client.stub = MagicMock()
    client.stub.Set = AsyncMock(return_value=SetResponse())

    asyncio.run(
        client.set(
            update=[
                {"path": "/interfaces/interface[name=Management0]/config", "data": {"description": "gnmi update test"}},
            ],
        )
    )

    request = client.stub.Set.call_args.args[0]
    assert isinstance(request, SetRequest)
    assert list(request.extension) == []
