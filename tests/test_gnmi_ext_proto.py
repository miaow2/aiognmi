from google.protobuf.duration_pb2 import Duration

from aiognmi.proto.gnmi import gnmi_pb2
from aiognmi.proto.gnmi_ext.gnmi_ext_pb2 import (
    Commit,
    CommitRequest,
    ConfigSubscription,
    ConfigSubscriptionStart,
    ConfigSubscriptionSyncDone,
    Depth,
    Extension,
)


def test_upstream_gnmi_service_option_remains_0_10_0() -> None:
    assert gnmi_pb2.DESCRIPTOR.GetOptions().Extensions[gnmi_pb2.gnmi_service] == "0.10.0"


def test_commit_extension_can_be_encoded() -> None:
    extension = Extension(
        commit=Commit(
            id="change-1",
            commit=CommitRequest(rollback_duration=Duration(seconds=30)),
        )
    )

    assert extension.WhichOneof("ext") == "commit"
    assert extension.commit.WhichOneof("action") == "commit"
    assert extension.commit.commit.rollback_duration.seconds == 30


def test_depth_extension_can_be_encoded() -> None:
    extension = Extension(depth=Depth(level=2))

    assert extension.WhichOneof("ext") == "depth"
    assert extension.depth.level == 2


def test_config_subscription_extension_can_be_encoded() -> None:
    start = Extension(config_subscription=ConfigSubscription(start=ConfigSubscriptionStart()))
    sync_done = Extension(
        config_subscription=ConfigSubscription(
            sync_done=ConfigSubscriptionSyncDone(commit_confirm_id="change-1", server_commit_id="server-1", done=True)
        )
    )

    assert start.WhichOneof("ext") == "config_subscription"
    assert start.config_subscription.WhichOneof("action") == "start"
    assert sync_done.config_subscription.WhichOneof("action") == "sync_done"
    assert sync_done.config_subscription.sync_done.done is True
