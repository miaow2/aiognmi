import logging
import math

import grpc
from grpc.aio import EOF as GRPC_EOF
from grpc.aio import AioRpcError, Metadata

from aiognmi.models import Notification
from aiognmi.proto.gnmi.gnmi_pb2 import Error as SubscribeError
from aiognmi.proto.gnmi.gnmi_pb2 import (
    ModelData,
    Path,
    QOSMarking,
    SubscribeRequest,
    Subscription,
    SubscriptionList,
    SubscriptionMode,
)
from aiognmi.proto.gnmi.gnmi_pb2_grpc import gNMIStub
from aiognmi.proto.gnmi_ext.gnmi_ext_pb2 import Extension
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


def _get_subscription_mode(stream_mode: str | None) -> int:
    """
    Map a public `stream_mode` string to a `SubscriptionMode` value

    Args:
        stream_mode: how one Subscription triggers - "target_defined" (default), "on_change", or
          "sample", case-insensitive. Only meaningful under `mode="stream"`

    Returns:
        int: the matching `SubscriptionMode` value; falls back to TARGET_DEFINED on an unknown string
    """
    if stream_mode is None:
        return SubscriptionMode.Value("TARGET_DEFINED")

    try:
        return SubscriptionMode.Value(stream_mode.upper())
    except ValueError:
        logger.warning(f"Stream mode {stream_mode} is not supported in Subscription, setting target_defined")
        return SubscriptionMode.Value("TARGET_DEFINED")


def _seconds_to_nanoseconds(seconds: int | float | None, name: str) -> int:
    """
    Validate a seconds interval and convert it to nanoseconds for a Subscription field

    Args:
        seconds: interval in seconds as `int` or `float` (fractional seconds are allowed); `None`
          leaves the underlying proto field unset
        name: parameter name used in the raised `ValueError` message

    Returns:
        int: nanoseconds, computed with `round()` so fractional seconds are not truncated; `0` if
          `seconds` is `None`

    Raises:
        ValueError: if `seconds` is a `bool`, not a real number, negative, or a non-finite float
          (`nan`/`inf`)
    """
    if seconds is None:
        return 0

    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"{name} must be a non-negative number of seconds")

    return round(seconds * 1_000_000_000)


def _build_qos(qos: int | None) -> QOSMarking | None:
    """
    Validate a DSCP value and wrap it in a `QOSMarking` message

    Args:
        qos: non-negative integer DSCP value; `None` leaves the `qos` field unset

    Returns:
        QOSMarking | None: the marking message, or `None` if `qos` is `None`

    Raises:
        ValueError: if `qos` is a `bool`, not an integer, or negative
    """
    if qos is None:
        return None

    if isinstance(qos, bool) or not isinstance(qos, int) or qos < 0:
        raise ValueError("qos must be a non-negative integer")

    return QOSMarking(marking=qos)


def _build_subscription(
    item: str | dict,
    stream_mode: str | None,
    sample_interval: int | float | None,
    heartbeat_interval: int | float | None,
    suppress_redundant: bool,
) -> Subscription:
    """
    Build a single `Subscription` from a bare path string or a per-path options dict

    Args:
        item: an xpath string, or a dict with keys `path`, `stream_mode`, `sample_interval`,
          `heartbeat_interval`, `suppress_redundant`. A dict key that is omitted (or a bare string)
          falls back to the corresponding method-level default argument below
        stream_mode: method-level default `stream_mode`
        sample_interval: method-level default `sample_interval` in seconds
        heartbeat_interval: method-level default `heartbeat_interval` in seconds
        suppress_redundant: method-level default `suppress_redundant`

    Returns:
        Subscription: the built Subscription message

    Raises:
        ValueError: if `item` is a dict missing `path`, or if the resolved `sample_interval`/
          `heartbeat_interval` is invalid (see `_seconds_to_nanoseconds`)
    """
    if isinstance(item, dict):
        if not item.get("path"):
            raise ValueError("subscriptions dict item must include a 'path' key")
        path = item["path"]
        stream_mode = item.get("stream_mode", stream_mode)
        sample_interval = item.get("sample_interval", sample_interval)
        heartbeat_interval = item.get("heartbeat_interval", heartbeat_interval)
        suppress_redundant = item.get("suppress_redundant", suppress_redundant)
    else:
        path = item

    return Subscription(
        path=create_gnmi_path(path),
        mode=_get_subscription_mode(stream_mode),
        sample_interval=_seconds_to_nanoseconds(sample_interval, "sample_interval"),
        heartbeat_interval=_seconds_to_nanoseconds(heartbeat_interval, "heartbeat_interval"),
        suppress_redundant=bool(suppress_redundant),
    )


def build_subscription_list(
    prefix: Path,
    subscriptions: list[str | dict],
    mode: str | None,
    encoding: int,
    stream_mode: str | None = None,
    sample_interval: int | float | None = None,
    heartbeat_interval: int | float | None = None,
    suppress_redundant: bool = False,
    updates_only: bool = False,
    allow_aggregation: bool = False,
    qos: int | None = None,
    use_models: list[dict] | None = None,
) -> SubscriptionList:
    """
    Build a `SubscriptionList` from path strings/dicts and method-level per-Subscription defaults

    Args:
        prefix: gNMI Path to use as the SubscriptionList prefix
        subscriptions: list of items, each either an xpath string or a dict with keys `path`,
          `stream_mode`, `sample_interval`, `heartbeat_interval`, `suppress_redundant`. A bare
          string inherits every default below; a dict overrides only the keys it sets, and must
          always include `path`
        mode: how the request is delivered - "stream" (default), "once", or "poll"
        encoding: resolved gNMI Encoding value
        stream_mode: default per-Subscription trigger - "target_defined" (default), "on_change", or
          "sample" - for any item that omits its own `stream_mode`
        sample_interval: default sample interval in seconds (`int` or `float`; fractional seconds
          are allowed), converted internally to nanoseconds, for any item that omits its own
        heartbeat_interval: default heartbeat interval in seconds (`int` or `float`; fractional
          seconds are allowed), converted internally to nanoseconds, for any item that omits its own
        suppress_redundant: default `suppress_redundant` flag for any item that omits its own
        updates_only: ask the target to skip the initial dump and send only subsequent changes
        allow_aggregation: allow the target to aggregate Notifications where the schema permits
        qos: non-negative integer DSCP value for the target to mark telemetry with; unset if `None`
        use_models: schema models the target should use, as dicts with keys `name`,
          `organization`, `version` - the same shape the Capabilities result produces

    Returns:
        SubscriptionList: the built SubscriptionList message

    Raises:
        ValueError: if a dict item is missing `path`, if a `sample_interval`/`heartbeat_interval`
          (method-level or per-item) is negative, non-numeric, a `bool`, or a non-finite float, if
          `qos` is negative, non-integer, or a `bool`, or if a `use_models` dict has an unknown key
    """
    subscription_list = [
        _build_subscription(item, stream_mode, sample_interval, heartbeat_interval, suppress_redundant)
        for item in subscriptions
    ]

    return SubscriptionList(
        prefix=prefix,
        subscription=subscription_list,
        mode=_get_subscription_list_mode(mode),
        encoding=encoding,
        updates_only=bool(updates_only),
        allow_aggregation=bool(allow_aggregation),
        qos=_build_qos(qos),
        use_models=[ModelData(**model) for model in use_models or []],
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

    def __init__(
        self,
        stub: gNMIStub,
        credentials: list[tuple[str, str]],
        subscription_list: SubscriptionList,
        extensions: list[Extension] | None = None,
    ) -> None:
        """
        Args:
            stub: gNMI gRPC stub used to open the Subscribe call
            credentials: metadata passed to the Subscribe call
            subscription_list: SubscriptionList to send in the initial SubscribeRequest
            extensions: gNMI Extension messages to send in the initial SubscribeRequest
        """
        self._stub = stub
        self._credentials = credentials
        self._subscription_list = subscription_list
        self._extensions = list(extensions or [])
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
            await self._call.write(SubscribeRequest(subscribe=self._subscription_list, extension=self._extensions))
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
