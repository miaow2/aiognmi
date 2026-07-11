import asyncio
from collections.abc import Callable

import pytest

from aiognmi import AsyncgNMIClient, Extension, ExtensionID, RegisteredExtension
from aiognmi.proto.gnmi.gnmi_pb2 import GetRequest, SetRequest


def _make_extension(payload: bytes = b"payload") -> Extension:
    return Extension(
        registered_ext=RegisteredExtension(id=ExtensionID.Value("EID_EXPERIMENTAL"), msg=payload),
    )


def test_get_request_includes_extensions(client_with_mock_get: AsyncgNMIClient) -> None:
    extension = _make_extension()

    asyncio.run(client_with_mock_get.get(paths=["/interfaces/interface[name=Management0]"], extensions=[extension]))

    request = client_with_mock_get.stub.Get.call_args.args[0]
    assert isinstance(request, GetRequest)
    assert list(request.extension) == [extension]


def test_get_request_defaults_to_empty_extensions(client_with_mock_get: AsyncgNMIClient) -> None:
    asyncio.run(client_with_mock_get.get(paths=["/interfaces/interface[name=Management0]"]))

    request = client_with_mock_get.stub.Get.call_args.args[0]
    assert isinstance(request, GetRequest)
    assert list(request.extension) == []


@pytest.mark.parametrize("depth", [0, 2])
def test_get_request_includes_depth_extension(client_with_mock_get: AsyncgNMIClient, depth: int) -> None:
    asyncio.run(client_with_mock_get.get(paths=["/interfaces/interface[name=Management0]"], depth=depth))

    request = client_with_mock_get.stub.Get.call_args.args[0]
    assert len(request.extension) == 1
    assert request.extension[0].WhichOneof("ext") == "depth"
    assert request.extension[0].depth.level == depth


def test_get_depth_appends_to_caller_extensions(client_with_mock_get: AsyncgNMIClient) -> None:
    extension = _make_extension()
    extensions = [extension]

    asyncio.run(client_with_mock_get.get(extensions=extensions, depth=2))

    request = client_with_mock_get.stub.Get.call_args.args[0]
    assert request.extension[0] == extension
    assert request.extension[1].depth.level == 2
    assert extensions == [extension]


@pytest.mark.parametrize("depth", [-1, 1.5, "2", True])
def test_get_rejects_invalid_depth(make_client: Callable[..., AsyncgNMIClient], depth: object) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError, match="depth must be a non-negative integer"):
        asyncio.run(client.get(depth=depth))


def test_set_request_includes_extensions(client_with_mock_set: AsyncgNMIClient) -> None:
    extension = _make_extension()

    asyncio.run(
        client_with_mock_set.set(
            update=[
                {"path": "/interfaces/interface[name=Management0]/config", "data": {"description": "gnmi update test"}},
            ],
            extensions=[extension],
        )
    )

    request = client_with_mock_set.stub.Set.call_args.args[0]
    assert isinstance(request, SetRequest)
    assert list(request.extension) == [extension]


def test_set_union_replace_request_includes_extensions(client_with_mock_set: AsyncgNMIClient) -> None:
    extension = _make_extension()

    asyncio.run(
        client_with_mock_set.set(
            union_replace=[
                {"path": "/interfaces/interface[name=Management0]/config", "data": {"description": "gnmi update test"}},
            ],
            extensions=[extension],
        )
    )

    request = client_with_mock_set.stub.Set.call_args.args[0]
    assert isinstance(request, SetRequest)
    assert list(request.extension) == [extension]


def test_set_request_defaults_to_empty_extensions(client_with_mock_set: AsyncgNMIClient) -> None:
    asyncio.run(
        client_with_mock_set.set(
            update=[
                {"path": "/interfaces/interface[name=Management0]/config", "data": {"description": "gnmi update test"}},
            ],
        )
    )

    request = client_with_mock_set.stub.Set.call_args.args[0]
    assert isinstance(request, SetRequest)
    assert list(request.extension) == []


def test_set_commit_request(client_with_mock_set: AsyncgNMIClient) -> None:
    asyncio.run(
        client_with_mock_set.set(
            update=[{"path": "/system/config", "data": {"hostname": "router-1"}}],
            commit_id="change-1",
            commit_rollback_duration=30,
        )
    )

    request = client_with_mock_set.stub.Set.call_args.args[0]
    assert request.extension[0].commit.id == "change-1"
    assert request.extension[0].commit.WhichOneof("action") == "commit"
    assert request.extension[0].commit.commit.rollback_duration.seconds == 30
    assert len(request.update) == 1


@pytest.mark.parametrize(
    ("action_argument", "action_name"),
    [
        ({"commit_confirm": True}, "confirm"),
        ({"commit_cancel": True}, "cancel"),
        ({"commit_set_rollback_duration": 45}, "set_rollback_duration"),
    ],
)
def test_set_existing_commit_action(
    client_with_mock_set: AsyncgNMIClient, action_argument: dict, action_name: str
) -> None:
    asyncio.run(client_with_mock_set.set(commit_id="change-1", **action_argument))

    commit = client_with_mock_set.stub.Set.call_args.args[0].extension[0].commit
    assert commit.id == "change-1"
    assert commit.WhichOneof("action") == action_name
    if action_name == "set_rollback_duration":
        assert commit.set_rollback_duration.rollback_duration.seconds == 45


@pytest.mark.parametrize(
    "commit_arguments",
    [
        {"commit_rollback_duration": 30},
        {"commit_confirm": True},
        {"commit_cancel": True},
        {"commit_set_rollback_duration": 30},
    ],
)
def test_set_commit_action_requires_commit_id(
    make_client: Callable[..., AsyncgNMIClient], commit_arguments: dict
) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError, match="commit_id is required"):
        asyncio.run(client.set(**commit_arguments))


def test_set_commit_requires_exactly_one_action(make_client: Callable[..., AsyncgNMIClient]) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError, match="exactly one"):
        asyncio.run(client.set(commit_id="change-1"))

    with pytest.raises(ValueError, match="exactly one"):
        asyncio.run(client.set(commit_id="change-1", commit_confirm=True, commit_cancel=True))


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("commit_rollback_duration", 0),
        ("commit_rollback_duration", -1),
        ("commit_rollback_duration", 1.5),
        ("commit_rollback_duration", True),
        ("commit_set_rollback_duration", 0),
        ("commit_set_rollback_duration", -1),
        ("commit_set_rollback_duration", "30"),
        ("commit_set_rollback_duration", False),
    ],
)
def test_set_commit_rejects_invalid_rollback_duration(
    make_client: Callable[..., AsyncgNMIClient], argument: str, value: object
) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError, match=f"{argument} must be a positive integer"):
        asyncio.run(client.set(commit_id="change-1", **{argument: value}))


def test_set_commit_accepts_truthy_action_flags(client_with_mock_set: AsyncgNMIClient) -> None:
    asyncio.run(client_with_mock_set.set(commit_id="change-1", commit_confirm=1))

    commit = client_with_mock_set.stub.Set.call_args.args[0].extension[0].commit
    assert commit.WhichOneof("action") == "confirm"


def test_set_commit_appends_to_caller_extensions(client_with_mock_set: AsyncgNMIClient) -> None:
    extension = _make_extension()
    extensions = [extension]

    asyncio.run(client_with_mock_set.set(extensions=extensions, commit_id="change-1", commit_confirm=True))

    request = client_with_mock_set.stub.Set.call_args.args[0]
    assert request.extension[0] == extension
    assert request.extension[1].commit.WhichOneof("action") == "confirm"
    assert extensions == [extension]
