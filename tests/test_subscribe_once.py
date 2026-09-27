import asyncio
import inspect
from collections.abc import Callable
from typing import Any

import grpc
import pytest
from grpc.aio import AioRpcError

from aiognmi import AsyncgNMIClient
from aiognmi.models import GetResult, SubscribeResult
from aiognmi.proto.gnmi.gnmi_pb2 import Error as ProtoError
from aiognmi.proto.gnmi.gnmi_pb2 import Notification as ProtoNotification
from aiognmi.proto.gnmi.gnmi_pb2 import SubscribeResponse, SubscriptionList, SubscriptionMode
from aiognmi.response import Response
from aiognmi.utils import create_gnmi_path, parse_notification

STREAM_ONLY_OPTIONS = [
    ("stream_mode", "sample"),
    ("sample_interval", 10),
    ("heartbeat_interval", 30),
    ("suppress_redundant", True),
]


def _notification_response(path: str, value: str) -> SubscribeResponse:
    notification = ProtoNotification(timestamp=1234)
    notification.update.add(path=create_gnmi_path(path))
    notification.update[0].val.string_val = value
    return SubscribeResponse(update=notification)


def _unavailable(details: str) -> AioRpcError:
    return AioRpcError(
        code=grpc.StatusCode.UNAVAILABLE,
        initial_metadata=None,
        trailing_metadata=None,
        details=details,
    )


def test_subscribe_once_returns_response_carrying_notifications(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    first = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    second = _notification_response("/interfaces/interface[name=eth1]/state/oper-status", "DOWN")
    client, call = make_subscribe_client([first, second, SubscribeResponse(sync_response=True)])

    response = asyncio.run(client.subscribe_once(subscriptions=["/interfaces"]))

    assert isinstance(response, Response)
    assert response.failed is False
    assert response.target == client.target
    assert response.elapsed_time is not None
    assert response.result == {
        "notifications": [parse_notification(first.update).dict(), parse_notification(second.update).dict()]
    }


def test_subscribe_once_with_no_notifications_returns_empty_result(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    client, call = make_subscribe_client([SubscribeResponse(sync_response=True)])

    response = asyncio.run(client.subscribe_once(subscriptions=["/interfaces"]))

    assert response.failed is False
    assert response.result == {"notifications": []}


def test_subscribe_once_sends_once_mode_request(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    client, call = make_subscribe_client([])

    asyncio.run(client.subscribe_once(subscriptions=["/interfaces", "/system"]))

    assert len(call.written) == 1
    subscription_list = call.written[0].subscribe
    assert subscription_list.mode == SubscriptionList.Mode.Value("ONCE")
    assert subscription_list.prefix.target == client.target
    assert [s.path for s in subscription_list.subscription] == [
        create_gnmi_path("/interfaces"),
        create_gnmi_path("/system"),
    ]


def test_subscribe_once_cancels_call_after_draining(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    client, call = make_subscribe_client([SubscribeResponse(sync_response=True)])

    asyncio.run(client.subscribe_once(subscriptions=["/interfaces"]))

    assert call.cancelled is True


def test_subscribe_once_records_read_error_on_failed_response(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    first = _notification_response("/interfaces/interface[name=eth0]/state/oper-status", "UP")
    client, call = make_subscribe_client([first, _unavailable("connection lost")])

    response = asyncio.run(client.subscribe_once(subscriptions=["/interfaces"]))

    assert response.failed is True
    assert response.result == "connection lost"
    assert isinstance(response.raw_result, AioRpcError)
    assert response.raw_result.code() == grpc.StatusCode.UNAVAILABLE
    assert response.elapsed_time is not None
    assert call.cancelled is True


def test_subscribe_once_records_write_error_on_failed_response(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    client, call = make_subscribe_client([], write_error=_unavailable("target unreachable"))

    response = asyncio.run(client.subscribe_once(subscriptions=["/interfaces"]))

    assert response.failed is True
    assert response.result == "target unreachable"
    assert call.cancelled is True


def test_subscribe_once_records_deprecated_error_field_on_failed_response(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    client, call = make_subscribe_client([SubscribeResponse(error=ProtoError(code=5, message="not found"))])

    response = asyncio.run(client.subscribe_once(subscriptions=["/interfaces"]))

    assert response.failed is True
    assert response.result == "not found"
    assert response.raw_result.code() == grpc.StatusCode.NOT_FOUND


def test_subscribe_once_failure_matches_get_failure(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
    client_with_mock_get: AsyncgNMIClient,
) -> None:
    error = _unavailable("connection lost")
    client, call = make_subscribe_client([error])
    client_with_mock_get.stub.Get.side_effect = error

    once_response = asyncio.run(client.subscribe_once(subscriptions=["/interfaces"]))
    get_response = asyncio.run(client_with_mock_get.get(paths=["/interfaces"]))

    assert (once_response.failed, once_response.result, once_response.debug_error_string) == (
        get_response.failed,
        get_response.result,
        get_response.debug_error_string,
    )


def test_subscribe_once_has_no_mode_parameter(make_client: Callable[..., AsyncgNMIClient]) -> None:
    client = make_client(insecure=True)

    assert "mode" not in inspect.signature(client.subscribe_once).parameters
    with pytest.raises(TypeError):
        asyncio.run(client.subscribe_once(subscriptions=["/interfaces"], mode="stream"))


@pytest.mark.parametrize("subscriptions", [None, []])
def test_subscribe_once_rejects_missing_or_empty_subscriptions(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]], subscriptions: list | None
) -> None:
    client, call = make_subscribe_client([])

    with pytest.raises(ValueError, match="subscriptions"):
        asyncio.run(client.subscribe_once(subscriptions=subscriptions))

    client.stub.Subscribe.assert_not_called()


def test_subscribe_once_passes_per_subscription_options_through(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    client, call = make_subscribe_client([])

    asyncio.run(
        client.subscribe_once(
            subscriptions=["/interfaces", {"path": "/system", "sample_interval": 5}],
            stream_mode="sample",
            sample_interval=0.5,
            heartbeat_interval=30,
            suppress_redundant=True,
        )
    )

    interfaces, system = call.written[0].subscribe.subscription
    assert interfaces.mode == SubscriptionMode.Value("SAMPLE")
    assert interfaces.sample_interval == 500_000_000
    assert interfaces.heartbeat_interval == 30_000_000_000
    assert interfaces.suppress_redundant is True
    assert system.sample_interval == 5_000_000_000


@pytest.mark.parametrize(("option", "value"), STREAM_ONLY_OPTIONS)
def test_subscribe_once_warns_on_stream_only_option_but_still_sends_request(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
    caplog: pytest.LogCaptureFixture,
    option: str,
    value: Any,
) -> None:
    client, call = make_subscribe_client([])

    with caplog.at_level("WARNING"):
        response = asyncio.run(client.subscribe_once(subscriptions=["/interfaces"], **{option: value}))

    assert response.failed is False
    assert len(call.written) == 1
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any(option in message and "ignore" in message for message in warnings)


@pytest.mark.parametrize(("option", "value"), STREAM_ONLY_OPTIONS)
def test_subscribe_with_once_mode_warns_on_stream_only_option_in_dict_item(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
    caplog: pytest.LogCaptureFixture,
    option: str,
    value: Any,
) -> None:
    client, call = make_subscribe_client([])

    async def _run() -> None:
        async with client.subscribe(subscriptions=[{"path": "/interfaces", option: value}], mode="once"):
            pass

    with caplog.at_level("WARNING"):
        asyncio.run(_run())

    assert len(call.written) == 1
    assert call.written[0].subscribe.mode == SubscriptionList.Mode.Value("ONCE")
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any(option in message and "ignore" in message for message in warnings)


def test_subscribe_once_does_not_warn_without_stream_only_options(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, call = make_subscribe_client([])

    with caplog.at_level("WARNING"):
        asyncio.run(client.subscribe_once(subscriptions=["/interfaces"]))

    assert [r for r in caplog.records if r.levelname == "WARNING"] == []


@pytest.mark.parametrize(("option", "value"), STREAM_ONLY_OPTIONS)
def test_stream_mode_does_not_warn_on_stream_only_option(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
    caplog: pytest.LogCaptureFixture,
    option: str,
    value: Any,
) -> None:
    client, call = make_subscribe_client([])

    with caplog.at_level("WARNING"):
        client.subscribe(subscriptions=["/interfaces"], **{option: value})

    assert [r for r in caplog.records if r.levelname == "WARNING"] == []


def test_subscribe_result_serialises_like_get_result() -> None:
    notifications = [parse_notification(_notification_response("/interfaces", "UP").update)]

    assert SubscribeResult(notifications=notifications).dict() == GetResult(notifications=notifications).dict()
    assert SubscribeResult().dict() == {"notifications": []}


def test_subscribe_once_passes_subscription_list_options_through(
    make_subscribe_client: Callable[..., tuple[AsyncgNMIClient, Any]],
) -> None:
    client, call = make_subscribe_client([])

    asyncio.run(
        client.subscribe_once(
            subscriptions=["state/counters"],
            prefix="/interfaces/interface[name=eth0]",
            target="leaf1",
            encoding="json_ietf",
            updates_only=True,
            allow_aggregation=True,
            qos=46,
            use_models=[{"name": "openconfig-interfaces", "organization": "OpenConfig", "version": "3.0.0"}],
            depth=2,
        )
    )

    request = call.written[0]
    subscription_list = request.subscribe
    assert subscription_list.mode == SubscriptionList.Mode.Value("ONCE")
    assert subscription_list.prefix == create_gnmi_path("/interfaces/interface[name=eth0]", "leaf1")
    assert subscription_list.encoding == client.get_encoding("json_ietf")
    assert subscription_list.updates_only is True
    assert subscription_list.allow_aggregation is True
    assert subscription_list.qos.marking == 46
    assert subscription_list.use_models[0].name == "openconfig-interfaces"
    assert request.extension[0].depth.level == 2
