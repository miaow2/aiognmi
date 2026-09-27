import asyncio
from collections.abc import Callable

import grpc
import pytest
from grpc.aio import AioRpcError

from aiognmi import AsyncgNMIClient, Extension, ExtensionID, RegisteredExtension, SubscribeStream
from aiognmi.models import Notification as NotificationModel
from aiognmi.proto.gnmi.gnmi_pb2 import (
    Encoding,
    SubscribeRequest,
    SubscribeResponse,
    Subscription,
    SubscriptionList,
    SubscriptionMode,
)
from aiognmi.proto.gnmi.gnmi_pb2 import Error as ProtoError
from aiognmi.proto.gnmi.gnmi_pb2 import Notification as ProtoNotification
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


@pytest.mark.parametrize(
    ("stream_mode", "expected"),
    [
        (None, SubscriptionMode.Value("TARGET_DEFINED")),
        ("target_defined", SubscriptionMode.Value("TARGET_DEFINED")),
        ("TARGET_DEFINED", SubscriptionMode.Value("TARGET_DEFINED")),
        ("on_change", SubscriptionMode.Value("ON_CHANGE")),
        ("On_Change", SubscriptionMode.Value("ON_CHANGE")),
        ("sample", SubscriptionMode.Value("SAMPLE")),
        ("Sample", SubscriptionMode.Value("SAMPLE")),
    ],
)
def test_subscribe_stream_mode_maps_to_subscription_mode(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], stream_mode: str | None, expected: int
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], stream_mode=stream_mode):
            pass

    asyncio.run(_run())

    assert call.written[0].subscribe.subscription[0].mode == expected


def test_subscribe_unknown_stream_mode_warns_and_falls_back_to_target_defined(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], stream_mode="bogus"):
            pass

    with caplog.at_level("WARNING"):
        asyncio.run(_run())

    assert call.written[0].subscribe.subscription[0].mode == SubscriptionMode.Value("TARGET_DEFINED")
    assert any("bogus" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("seconds", "expected_nanoseconds"),
    [
        (None, 0),
        (0, 0),
        (10, 10_000_000_000),
        (0.5, 500_000_000),
        (0.3, 300_000_000),
    ],
)
def test_subscribe_sample_interval_converts_seconds_to_nanoseconds(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    seconds: int | float | None,
    expected_nanoseconds: int,
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], stream_mode="sample", sample_interval=seconds):
            pass

    asyncio.run(_run())

    assert call.written[0].subscribe.subscription[0].sample_interval == expected_nanoseconds


@pytest.mark.parametrize(
    ("seconds", "expected_nanoseconds"),
    [
        (None, 0),
        (0, 0),
        (10, 10_000_000_000),
        (0.5, 500_000_000),
        (0.3, 300_000_000),
    ],
)
def test_subscribe_heartbeat_interval_converts_seconds_to_nanoseconds(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    seconds: int | float | None,
    expected_nanoseconds: int,
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], heartbeat_interval=seconds):
            pass

    asyncio.run(_run())

    assert call.written[0].subscribe.subscription[0].heartbeat_interval == expected_nanoseconds


@pytest.mark.parametrize("suppress_redundant", [True, False])
def test_subscribe_suppress_redundant_reaches_subscription(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], suppress_redundant: bool
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=["/interfaces"], suppress_redundant=suppress_redundant):
            pass

    asyncio.run(_run())

    assert call.written[0].subscribe.subscription[0].suppress_redundant is suppress_redundant


def test_subscribe_dict_overrides_method_level_defaults(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(
            subscriptions=[
                {
                    "path": "/interfaces/interface[name=eth0]/state/counters",
                    "stream_mode": "sample",
                    "sample_interval": 10,
                }
            ],
            stream_mode="on_change",
            sample_interval=5,
        ):
            pass

    asyncio.run(_run())

    subscription = call.written[0].subscribe.subscription[0]
    assert subscription.mode == SubscriptionMode.Value("SAMPLE")
    assert subscription.sample_interval == 10_000_000_000


def test_subscribe_string_items_inherit_method_level_defaults(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(
            subscriptions=["/interfaces/interface[name=eth0]/state/oper-status"],
            stream_mode="on_change",
            suppress_redundant=True,
        ):
            pass

    asyncio.run(_run())

    subscription = call.written[0].subscribe.subscription[0]
    assert subscription.mode == SubscriptionMode.Value("ON_CHANGE")
    assert subscription.suppress_redundant is True


def test_subscribe_mixed_list_of_strings_and_dicts(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(
            subscriptions=[
                {
                    "path": "/interfaces/interface[name=eth0]/state/counters",
                    "stream_mode": "sample",
                    "sample_interval": 10,
                },
                "/interfaces/interface[name=eth0]/state/oper-status",
            ],
            stream_mode="on_change",
        ):
            pass

    asyncio.run(_run())

    subscriptions: list[Subscription] = list(call.written[0].subscribe.subscription)
    assert subscriptions[0].mode == SubscriptionMode.Value("SAMPLE")
    assert subscriptions[0].sample_interval == 10_000_000_000
    assert subscriptions[1].mode == SubscriptionMode.Value("ON_CHANGE")


def test_subscribe_dict_missing_path_raises_value_error(
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError, match="path"):
        client.subscribe(subscriptions=[{"stream_mode": "sample", "sample_interval": 10}])


@pytest.mark.parametrize("interval", [-1, -0.5, "10", True, float("nan"), float("inf")])
@pytest.mark.parametrize("argument", ["sample_interval", "heartbeat_interval"])
def test_subscribe_rejects_invalid_interval_at_method_level(
    make_client: Callable[..., AsyncgNMIClient], argument: str, interval: object
) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError, match=f"{argument} must be a non-negative number of seconds"):
        client.subscribe(subscriptions=["/interfaces"], **{argument: interval})


@pytest.mark.parametrize("interval", [-1, -0.5, "10", True, float("nan"), float("inf")])
@pytest.mark.parametrize("argument", ["sample_interval", "heartbeat_interval"])
def test_subscribe_rejects_invalid_interval_per_dict_item(
    make_client: Callable[..., AsyncgNMIClient], argument: str, interval: object
) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError, match=f"{argument} must be a non-negative number of seconds"):
        client.subscribe(subscriptions=[{"path": "/interfaces", argument: interval}])


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


def _make_extension(payload: bytes = b"payload") -> Extension:
    return Extension(
        registered_ext=RegisteredExtension(id=ExtensionID.Value("EID_EXPERIMENTAL"), msg=payload),
    )


def _written_request(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], **kwargs: object
) -> tuple[AsyncgNMIClient, SubscribeRequest]:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(**kwargs):
            pass

    asyncio.run(_run())

    assert len(call.written) == 1
    return client, call.written[0]


@pytest.mark.parametrize("mode", ["stream", "once", "poll"])
def test_subscribe_prefix_and_target_reach_request_like_get(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], mode: str
) -> None:
    _, request = _written_request(
        make_subscribe_client,
        subscriptions=["state/counters"],
        mode=mode,
        prefix="/interfaces/interface[name=eth0]",
        target="leaf1",
    )

    assert request.subscribe.prefix == create_gnmi_path("/interfaces/interface[name=eth0]", "leaf1")


def test_subscribe_prefix_defaults_target_to_client_target(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    client, request = _written_request(make_subscribe_client, subscriptions=["state"], prefix="/interfaces")

    assert request.subscribe.prefix == create_gnmi_path("/interfaces", client.target)


@pytest.mark.parametrize(
    ("encoding", "expected"),
    [
        (None, Encoding.Value("JSON")),
        ("json_ietf", Encoding.Value("JSON_IETF")),
        ("PROTO", Encoding.Value("PROTO")),
    ],
)
def test_subscribe_encoding_reaches_subscription_list(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], encoding: str | None, expected: int
) -> None:
    _, request = _written_request(make_subscribe_client, subscriptions=["/interfaces"], encoding=encoding)

    assert request.subscribe.encoding == expected


def test_subscribe_unknown_encoding_warns_and_falls_back_to_client_default(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        _, request = _written_request(make_subscribe_client, subscriptions=["/interfaces"], encoding="bogus")

    assert request.subscribe.encoding == Encoding.Value("JSON")
    assert any("bogus" in record.message for record in caplog.records)


def test_subscribe_subscription_list_options_default_to_unset(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    _, request = _written_request(make_subscribe_client, subscriptions=["/interfaces"])

    subscription_list = request.subscribe
    assert subscription_list.updates_only is False
    assert subscription_list.allow_aggregation is False
    assert not subscription_list.HasField("qos")
    assert list(subscription_list.use_models) == []
    assert list(request.extension) == []


@pytest.mark.parametrize("mode", ["stream", "once", "poll"])
def test_subscribe_subscription_list_options_reach_request(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], mode: str
) -> None:
    use_models = [
        {"name": "openconfig-interfaces", "organization": "OpenConfig working group", "version": "3.0.0"},
        {"name": "openconfig-system", "organization": "OpenConfig working group", "version": "1.0.0"},
    ]

    _, request = _written_request(
        make_subscribe_client,
        subscriptions=["/interfaces"],
        mode=mode,
        updates_only=True,
        allow_aggregation=True,
        qos=46,
        use_models=use_models,
    )

    subscription_list = request.subscribe
    assert subscription_list.updates_only is True
    assert subscription_list.allow_aggregation is True
    assert subscription_list.qos.marking == 46
    assert [
        {"name": model.name, "organization": model.organization, "version": model.version}
        for model in subscription_list.use_models
    ] == use_models


def test_subscribe_qos_zero_is_sent(make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]]) -> None:
    _, request = _written_request(make_subscribe_client, subscriptions=["/interfaces"], qos=0)

    assert request.subscribe.HasField("qos")
    assert request.subscribe.qos.marking == 0


def test_subscribe_use_models_dict_with_unknown_key_raises_value_error(
    make_client: Callable[..., AsyncgNMIClient],
) -> None:
    client = make_client(insecure=True)

    with pytest.raises(ValueError):
        client.subscribe(subscriptions=["/interfaces"], use_models=[{"name": "openconfig-interfaces", "bogus": "x"}])


def test_subscribe_request_includes_extensions(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    extension = _make_extension()

    _, request = _written_request(make_subscribe_client, subscriptions=["/interfaces"], extensions=[extension])

    assert list(request.extension) == [extension]


@pytest.mark.parametrize("depth", [0, 2])
def test_subscribe_request_includes_depth_extension(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], depth: int
) -> None:
    _, request = _written_request(make_subscribe_client, subscriptions=["/interfaces"], depth=depth)

    assert len(request.extension) == 1
    assert request.extension[0].WhichOneof("ext") == "depth"
    assert request.extension[0].depth.level == depth


def test_subscribe_depth_appends_to_caller_extensions(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]],
) -> None:
    extension = _make_extension()
    extensions = [extension]

    _, request = _written_request(make_subscribe_client, subscriptions=["/interfaces"], extensions=extensions, depth=2)

    assert request.extension[0] == extension
    assert request.extension[1].depth.level == 2
    assert extensions == [extension]


@pytest.mark.parametrize("value", [-1, 1.5, "2", True])
@pytest.mark.parametrize("argument", ["qos", "depth"])
def test_subscribe_rejects_invalid_qos_and_depth(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, object]], argument: str, value: object
) -> None:
    client, _ = make_subscribe_client([])

    with pytest.raises(ValueError, match=f"{argument} must be a non-negative integer"):
        client.subscribe(subscriptions=["/interfaces"], **{argument: value})

    client.stub.Subscribe.assert_not_called()
