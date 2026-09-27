import asyncio
from collections.abc import Callable

import grpc
import pytest
from grpc.aio import AioRpcError

from aiognmi import AsyncgNMIClient
from aiognmi.proto.gnmi.gnmi_pb2 import Error as ProtoError
from aiognmi.proto.gnmi.gnmi_pb2 import Notification as ProtoNotification
from aiognmi.proto.gnmi.gnmi_pb2 import SubscribeResponse, SubscriptionList
from aiognmi.utils import create_gnmi_path, parse_notification

SYNC = SubscribeResponse(sync_response=True)


def _notification_response(path: str, value: str) -> SubscribeResponse:
    notification = ProtoNotification()
    notification.update.add(path=create_gnmi_path(path))
    notification.update[0].val.string_val = value
    return SubscribeResponse(update=notification)


def test_poll_mode_maps_to_poll_subscription_list_mode(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll"):
            pass

    asyncio.run(_run())

    assert len(call.written) == 1
    assert call.written[0].subscribe.mode == SubscriptionList.Mode.Value("POLL")


def test_poll_writes_poll_request_and_returns_batch_up_to_sync_response(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    first = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    second = _notification_response("/interfaces/interface[name=eth1]/state/oper-status", "DOWN")
    after_sync = _notification_response("/interfaces/interface[name=eth2]/state/oper-status", "UP")
    client, call = make_subscribe_client([first, second, SYNC, after_sync, SYNC])

    async def _run() -> list:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            return await stream.poll()

    batch = asyncio.run(_run())

    assert batch == [parse_notification(first.update), parse_notification(second.update)]
    assert len(call.written) == 2
    assert call.written[1].WhichOneof("request") == "poll"


def test_second_poll_returns_next_batch(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    first = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    second = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "DOWN")
    third = _notification_response("/interfaces/interface[name=eth1]/state/oper-status", "UP")
    client, call = make_subscribe_client([first, SYNC, second, third, SYNC])

    async def _run() -> tuple[list, list]:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            return await stream.poll(), await stream.poll()

    batch_one, batch_two = asyncio.run(_run())

    assert batch_one == [parse_notification(first.update)]
    assert batch_two == [parse_notification(second.update), parse_notification(third.update)]
    assert [request.WhichOneof("request") for request in call.written] == ["subscribe", "poll", "poll"]


def test_poll_returns_empty_batch_when_cycle_has_no_notifications(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([SYNC])

    async def _run() -> list:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            return await stream.poll()

    assert asyncio.run(_run()) == []


def test_synced_stays_true_across_poll_cycles(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    response = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    client, call = make_subscribe_client([response, SYNC, response, SYNC])
    observed: list[bool] = []

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            observed.append(stream.synced)
            await stream.poll()
            observed.append(stream.synced)
            await stream.poll()
            observed.append(stream.synced)

    asyncio.run(_run())

    assert observed == [False, True, True]


def test_iterating_poll_mode_stream_raises_runtime_error_naming_poll(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    response = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    client, call = make_subscribe_client([response, SYNC])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            async for _ in stream:
                pass

    with pytest.raises(RuntimeError, match=r"poll\(\)"):
        asyncio.run(_run())

    assert call.cancelled is True


def test_poll_on_stream_mode_stream_raises_runtime_error(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([SYNC])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"]) as stream:
            await stream.poll()

    with pytest.raises(RuntimeError, match="poll-mode"):
        asyncio.run(_run())

    assert len(call.written) == 1


def test_poll_on_stream_never_entered_raises_runtime_error(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([SYNC])
    stream = client.subscribe(subscriptions=["/interfaces"], mode="poll")

    with pytest.raises(RuntimeError, match="async with"):
        asyncio.run(stream.poll())

    client.stub.Subscribe.assert_not_called()


def test_poll_after_exit_raises_runtime_error(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([SYNC])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            pass
        await stream.poll()

    with pytest.raises(RuntimeError, match="closed"):
        asyncio.run(_run())

    assert len(call.written) == 1


def test_read_error_propagates_out_of_poll(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    error = AioRpcError(
        code=grpc.StatusCode.UNAVAILABLE,
        initial_metadata=None,
        trailing_metadata=None,
        details="connection lost",
    )
    response = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    client, call = make_subscribe_client([response, error])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            await stream.poll()

    with pytest.raises(AioRpcError, match="connection lost"):
        asyncio.run(_run())

    assert call.cancelled is True


def test_deprecated_error_field_raises_out_of_poll(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    error_response = SubscribeResponse(error=ProtoError(code=grpc.StatusCode.NOT_FOUND.value[0], message="not found"))
    client, call = make_subscribe_client([error_response])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            await stream.poll()

    with caplog.at_level("WARNING"), pytest.raises(AioRpcError) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND
    assert any("not found" in record.message for record in caplog.records)


def test_stream_ending_before_sync_response_raises_out_of_poll(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    response = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    client, call = make_subscribe_client([response])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
            await stream.poll()

    with pytest.raises(EOFError, match="Sync Response"):
        asyncio.run(_run())


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("stream_mode", "sample"),
        ("sample_interval", 10),
        ("heartbeat_interval", 30),
        ("suppress_redundant", True),
    ],
)
@pytest.mark.parametrize("per_path", [False, True], ids=["method_level", "per_path"])
def test_stream_only_option_under_poll_warns_but_still_sends_request(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    caplog: pytest.LogCaptureFixture,
    option: str,
    value: object,
    per_path: bool,
) -> None:
    client, call = make_subscribe_client([])
    if per_path:
        kwargs = {"subscriptions": [{"path": "/interfaces", option: value}]}
    else:
        kwargs = {"subscriptions": ["/interfaces"], option: value}

    async def _run() -> None:
        async with client.subscribe(mode="poll", **kwargs):
            pass

    with caplog.at_level("WARNING"):
        asyncio.run(_run())

    warnings = [record.message for record in caplog.records if record.levelname == "WARNING"]
    assert any(option in message and "poll" in message for message in warnings)
    assert len(call.written) == 1
    assert call.written[0].subscribe.mode == SubscriptionList.Mode.Value("POLL")
    assert len(call.written[0].subscribe.subscription) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "poll"},
        {"mode": "stream", "stream_mode": "sample", "sample_interval": 10},
        {"stream_mode": "on_change", "heartbeat_interval": 30, "suppress_redundant": True},
    ],
    ids=["poll_without_stream_options", "explicit_stream_mode", "default_stream_mode"],
)
def test_no_ignored_option_warning_when_options_apply(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    caplog: pytest.LogCaptureFixture,
    kwargs: dict,
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], **kwargs):
            pass

    with caplog.at_level("WARNING"):
        asyncio.run(_run())

    assert not any("ignore" in record.message for record in caplog.records)
