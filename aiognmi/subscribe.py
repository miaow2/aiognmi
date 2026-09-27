import logging

import grpc
from grpc.aio import EOF as GRPC_EOF
from grpc.aio import AioRpcError, Metadata

from aiognmi.models import Notification
from aiognmi.proto.gnmi.gnmi_pb2 import Error as SubscribeError
from aiognmi.proto.gnmi.gnmi_pb2 import Path, SubscribeRequest, Subscription, SubscriptionList
from aiognmi.proto.gnmi.gnmi_pb2_grpc import gNMIStub
from aiognmi.utils import create_gnmi_path, parse_notification

logger = logging.getLogger(__name__)

_STATUS_CODES_BY_VALUE = {code.value[0]: code for code in grpc.StatusCode}


def _get_subscription_list_mode(mode: str | None) -> int:
    """
    Map a public `mode` string to a `SubscriptionList.Mode` value

    Args:
        mode: "stream" (default), "once", or "poll", case-insensitive

    Returns:
        int: the matching `SubscriptionList.Mode` value; falls back to STREAM on an unknown string
    """
    if mode is None:
        return SubscriptionList.Mode.Value("STREAM")

    try:
        return SubscriptionList.Mode.Value(mode.upper())
    except ValueError:
        logger.warning(f"Mode {mode} is not supported in SubscribeRequest, setting stream")
        return SubscriptionList.Mode.Value("STREAM")


def build_subscription_list(prefix: Path, paths: list[str], mode: str | None, encoding: int) -> SubscriptionList:
    """
    Build a `SubscriptionList` from bare path strings and the default Stream Mode

    Args:
        prefix: gNMI Path to use as the SubscriptionList prefix
        paths: list of xpath strings to subscribe to
        mode: how the request is delivered - "stream" (default), "once", or "poll"
        encoding: resolved gNMI Encoding value

    Returns:
        SubscriptionList: the built SubscriptionList message
    """
    subscriptions = [Subscription(path=create_gnmi_path(path)) for path in paths]

    return SubscriptionList(
        prefix=prefix,
        subscription=subscriptions,
        mode=_get_subscription_list_mode(mode),
        encoding=encoding,
    )


def _build_stream_error(error: SubscribeError) -> AioRpcError:
    """
    Build an `AioRpcError` from a deprecated Subscribe response `Error` message

    Args:
        error: deprecated gNMI Error message received on a SubscribeResponse

    Returns:
        AioRpcError: exception carrying the mapped status code and error message
    """
    code = _STATUS_CODES_BY_VALUE.get(error.code, grpc.StatusCode.UNKNOWN)

    return AioRpcError(
        code=code,
        initial_metadata=Metadata(),
        trailing_metadata=Metadata(),
        details=error.message,
    )


class SubscribeStream:
    """
    An async context manager and async iterator over a gNMI Subscribe RPC

    The underlying call is opened, and the initial `SubscribeRequest` written, on `__aenter__`.
    Leaving the `async with` block - including via `break` or an exception - cancels the call.
    """

    def __init__(self, stub: gNMIStub, credentials: list[tuple[str, str]], subscription_list: SubscriptionList) -> None:
        """
        Args:
            stub: gNMI gRPC stub used to open the Subscribe call
            credentials: metadata passed to the Subscribe call
            subscription_list: SubscriptionList to send in the initial SubscribeRequest
        """
        self._stub = stub
        self._credentials = credentials
        self._subscription_list = subscription_list
        self._call = None
        self._entered = False
        self._closed = False
        self._synced = False

    @property
    def synced(self) -> bool:
        """
        Whether the target has sent every value at least once

        Returns:
            bool: False until the first Sync Response, permanently True afterwards
        """
        return self._synced

    async def __aenter__(self) -> "SubscribeStream":
        """
        Open the Subscribe call and write the initial SubscribeRequest

        Returns:
            SubscribeStream: self

        Raises:
            Any exception raised by the write() call; the underlying call is cancelled before re-raising
        """
        self._call = self._stub.Subscribe(metadata=self._credentials)
        try:
            await self._call.write(SubscribeRequest(subscribe=self._subscription_list))
        except BaseException:
            self._call.cancel()
            raise
        self._entered = True

        return self

    async def __aexit__(self, exc_type: type | None, exc: BaseException | None, tb: object | None) -> None:
        """
        Cancel the Subscribe call on exit, including via `break` or an exception
        """
        self._call.cancel()
        self._closed = True

    def __aiter__(self) -> "SubscribeStream":
        return self

    async def __anext__(self) -> Notification:
        """
        Read from the call until the next Notification, raising on a stream error

        Returns:
            Notification: the next parsed Notification

        Raises:
            RuntimeError: if the stream was never entered with `async with`, or if iteration is attempted
              after the stream is closed
            AioRpcError: if the call's read() raises, or the target sends the deprecated error field
        """
        if not self._entered:
            raise RuntimeError("SubscribeStream must be entered with 'async with' before it can be iterated")

        if self._closed:
            raise RuntimeError("SubscribeStream is closed")

        while True:
            response = await self._call.read()
            if response is GRPC_EOF:
                raise StopAsyncIteration

            which = response.WhichOneof("response")
            if which == "update":
                return parse_notification(response.update)
            elif which == "sync_response":
                self._synced = True
                continue
            elif which == "error":
                logger.warning(f"Subscribe response carried a deprecated error: {response.error.message}")
                raise _build_stream_error(response.error)
