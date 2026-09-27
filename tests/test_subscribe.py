import asyncio
from collections.abc import Callable

import grpc
import pytest
from grpc.aio import AioRpcError

from aiognmi import AsyncgNMIClient, SubscribeStream
from aiognmi.models import Notification as NotificationModel
from aiognmi.proto.gnmi.gnmi_pb2 import Error as ProtoError
from aiognmi.proto.gnmi.gnmi_pb2 import Notification as ProtoNotification
from aiognmi.proto.gnmi.gnmi_pb2 import SubscribeRequest, SubscribeResponse, SubscriptionList
from aiognmi.utils import create_gnmi_path, parse_notification


@pytest.mark.parametrize("subscriptions", [None, []])
def test_subscribe_rejects_missing_or_empty_subscriptions(
    make_client: Callable[..., AsyncgNMIClient], subscriptions: list | None
) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError, match="subscriptions"):
        client.subscribe(subscriptions=subscriptions)


def test_subscribe_stream_is_importable_from_package_root() -> None:
    assert SubscribeStream is not None


def test_subscribe_returns_stream_without_opening_call(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([])

    stream = client.subscribe(subscriptions=["/interfaces"])

    assert isinstance(stream, SubscribeStream)
    client.stub.Subscribe.assert_not_called()
    assert call.written == []


def test_subscribe_writes_request_with_paths_prefix_target_and_default_mode(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces", "/system"]):
            pass

    asyncio.run(_run())

    assert len(call.written) == 1
    request = call.written[0]
    assert isinstance(request, SubscribeRequest)
    subscription_list = request.subscribe
    assert isinstance(subscription_list, SubscriptionList)
    assert subscription_list.prefix.target == client.target
    assert [s.path for s in subscription_list.subscription] == [
        create_gnmi_path("/interfaces"),
        create_gnmi_path("/system"),
    ]
    assert subscription_list.mode == SubscriptionList.Mode.Value("STREAM")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("stream", SubscriptionList.Mode.Value("STREAM")),
        ("STREAM", SubscriptionList.Mode.Value("STREAM")),
        ("once", SubscriptionList.Mode.Value("ONCE")),
        ("Once", SubscriptionList.Mode.Value("ONCE")),
        ("poll", SubscriptionList.Mode.Value("POLL")),
        ("Poll", SubscriptionList.Mode.Value("POLL")),
    ],
)
def test_subscribe_maps_mode_case_insensitively(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], mode: str, expected: int
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode=mode):
            pass

    asyncio.run(_run())

    assert call.written[0].subscribe.mode == expected


def test_subscribe_unknown_mode_warns_and_falls_back_to_stream(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode="bogus"):
            pass

    with caplog.at_level("WARNING"):
        asyncio.run(_run())

    assert call.written[0].subscribe.mode == SubscriptionList.Mode.Value("STREAM")
    assert any("bogus" in record.message for record in caplog.records)


def _notification_response(path: str, value: str) -> SubscribeResponse:
    notification = ProtoNotification(timestamp=1234)
    notification.update.add(path=create_gnmi_path(path))
    notification.update[0].val.string_val = value
    return SubscribeResponse(update=notification)


def test_iteration_yields_notifications_matching_scripted_responses(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    response = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    client, call = make_subscribe_client([response])
    collected: list[NotificationModel] = []

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"]) as stream:
            async for notification in stream:
                collected.append(notification)

    asyncio.run(_run())

    assert collected == [parse_notification(response.update)]


def test_synced_is_false_before_sync_response_true_after_and_stays_true(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    first = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    second = _notification_response("/interfaces/interface[name=eth0]/state/admin-status", "UP")
    client, call = make_subscribe_client([first, SubscribeResponse(sync_response=True), second])
    synced_before = None
    synced_after_sync = None

    async def _run() -> None:
        nonlocal synced_before, synced_after_sync
        async with client.subscribe(subscriptions=["/interfaces"]) as stream:
            assert stream.synced is False
            async for _ in stream:
                if synced_before is None:
                    synced_before = stream.synced
                else:
                    synced_after_sync = stream.synced

    asyncio.run(_run())

    assert synced_before is False
    assert synced_after_sync is True


def test_cancel_on_normal_exit(make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]]) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"]) as stream:
            async for _ in stream:
                pass

    asyncio.run(_run())

    assert call.cancelled is True


def test_cancel_on_break(make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]]) -> None:
    response = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    client, call = make_subscribe_client([response, response])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"]) as stream:
            async for _ in stream:
                break

    asyncio.run(_run())

    assert call.cancelled is True


def test_cancel_on_exception(make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]]) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"]):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(_run())

    assert call.cancelled is True


def test_read_error_propagates_out_of_async_for(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    error = AioRpcError(
        code=grpc.StatusCode.UNAVAILABLE,
        initial_metadata=None,
        trailing_metadata=None,
        details="connection lost",
    )
    client, call = make_subscribe_client([error])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"]) as stream:
            async for _ in stream:
                pass

    with pytest.raises(AioRpcError, match="connection lost"):
        asyncio.run(_run())


def test_deprecated_error_field_warns_and_raises_aio_rpc_error(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    error_response = SubscribeResponse(error=ProtoError(code=5, message="not found"))
    client, call = make_subscribe_client([error_response])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"]) as stream:
            async for _ in stream:
                pass

    with caplog.at_level("WARNING"), pytest.raises(AioRpcError) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND
    assert exc_info.value.details() == "not found"
    assert any("not found" in record.message for record in caplog.records)


def test_iterating_stream_never_entered_raises_runtime_error(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([])
    stream = client.subscribe(subscriptions=["/interfaces"])

    async def _run() -> None:
        async for _ in stream:
            pass

    with pytest.raises(RuntimeError, match="async with"):
        asyncio.run(_run())


def test_leak_when_write_fails_on_enter(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    """If write() fails in __aenter__, the call should be cancelled."""
    write_error = RuntimeError("write failed")
    client, call = make_subscribe_client(write_error=write_error)

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"]):
            pass

    with pytest.raises(RuntimeError, match="write failed"):
        asyncio.run(_run())

    assert call.cancelled is True


def test_iterating_after_exit_raises_runtime_error(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    """Iterating after exiting the async with block should raise RuntimeError."""
    response = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    client, call = make_subscribe_client([response])
    stream = None

    async def _run() -> None:
        nonlocal stream
        async with client.subscribe(subscriptions=["/interfaces"]) as s:
            stream = s
            async for _ in s:
                pass

        # Try to iterate after exiting
        async for _ in stream:
            pass

    with pytest.raises(RuntimeError, match="closed"):
        asyncio.run(_run())
