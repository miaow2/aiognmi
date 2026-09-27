import json

import pytest
from google.protobuf.any_pb2 import Any

from aiognmi.models import Notification
from aiognmi.proto.gnmi.gnmi_pb2 import Notification as ProtoNotification
from aiognmi.proto.gnmi.gnmi_pb2 import Path, PathElem, ScalarArray, TypedValue, Update
from aiognmi.utils import (
    create_gnmi_path,
    create_update_obj,
    create_xpath,
    get_origin,
    parse_key_value,
    parse_notification,
    split_path,
)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("", ("", None)),
        ("/", ("/", None)),
        ("yang-module:container/container[key=value]", ("container/container[key=value]", "yang-module")),
        ("container/container[key=value]", ("container/container[key=value]", None)),
    ],
)
def test_get_origin(path: str, expected: tuple) -> None:
    assert get_origin(path) == expected


@pytest.mark.parametrize(
    "path, expected",
    [
        ("", []),
        ("/", []),
        ("container/container[key=value]", ["container", "container[key=value]"]),
        ("container/container[key=value]/", ["container", "container[key=value]"]),
        ("container/container[ip=1.1.1.1/32]", ["container", "container[ip=1.1.1.1/32]"]),
        ("container/container[name=test][ip=1.1.1.1/32]", ["container", "container[name=test][ip=1.1.1.1/32]"]),
        (
            "container/container[name=test]/config[ip=1.1.1.1/32]",
            ["container", "container[name=test]", "config[ip=1.1.1.1/32]"],
        ),
    ],
)
def test_split_path(path: str, expected: list) -> None:
    assert split_path(path) == expected


@pytest.mark.parametrize(
    "path, expected",
    [
        ("", {}),
        ("[k1=v1]", {"k1": "v1"}),
        ("[k1=v1][k2=v2]", {"k1": "v1", "k2": "v2"}),
    ],
)
def test_parse_key_value(path: str, expected: dict) -> None:
    assert parse_key_value(path) == expected


@pytest.mark.parametrize(
    "path, expected",
    [
        ("", Path(elem=[], origin="openconfig")),
        ("/", Path(elem=[], origin="openconfig")),
        ("openconfig:", Path(origin="openconfig", elem=[])),
        ("openconfig:/", Path(origin="openconfig", elem=[])),
        (
            "containers/container",
            Path(origin="openconfig", elem=[PathElem(name="containers"), PathElem(name="container")]),
        ),
        (
            "/containers/container",
            Path(origin="openconfig", elem=[PathElem(name="containers"), PathElem(name="container")]),
        ),
        (
            "yang:containers/container",
            Path(origin="yang", elem=[PathElem(name="containers"), PathElem(name="container")]),
        ),
        (
            "yang:openconfig:containers/container",
            Path(origin="yang", elem=[PathElem(name="openconfig:containers"), PathElem(name="container")]),
        ),
        (
            "containers/container[key=value]",
            Path(
                origin="openconfig",
                elem=[PathElem(name="containers"), PathElem(name="container", key={"key": "value"})],
            ),
        ),
        (
            "/containers/container[key=value]",
            Path(
                origin="openconfig",
                elem=[PathElem(name="containers"), PathElem(name="container", key={"key": "value"})],
            ),
        ),
        (
            "yang:containers/container[key=value]",
            Path(origin="yang", elem=[PathElem(name="containers"), PathElem(name="container", key={"key": "value"})]),
        ),
        (
            "containers/container[key=value]",
            Path(
                origin="openconfig",
                elem=[PathElem(name="containers"), PathElem(name="container", key={"key": "value"})],
            ),
        ),
        (
            "containers/container[key=value]/config/test",
            Path(
                origin="openconfig",
                elem=[
                    PathElem(name="containers"),
                    PathElem(name="container", key={"key": "value"}),
                    PathElem(name="config"),
                    PathElem(name="test"),
                ],
            ),
        ),
        (
            "yang:containers/container[key=value]/config/ip[ip=2001:db8:0:2::/64]",
            Path(
                origin="yang",
                elem=[
                    PathElem(name="containers"),
                    PathElem(name="container", key={"key": "value"}),
                    PathElem(name="config"),
                    PathElem(name="ip", key={"ip": "2001:db8:0:2::/64"}),
                ],
            ),
        ),
        (
            "containers/container[key1=value1][key2=]/test:config/ip[ip=2001:db8:0:2::/64]",
            Path(
                origin="openconfig",
                elem=[
                    PathElem(name="containers"),
                    PathElem(name="container", key={"key1": "value1", "key2": ""}),
                    PathElem(name="test:config"),
                    PathElem(name="ip", key={"ip": "2001:db8:0:2::/64"}),
                ],
            ),
        ),
    ],
)
def test_create_gnmi_path(path: str, expected: Path) -> None:
    gnmi_path = create_gnmi_path(path)
    assert expected.origin == gnmi_path.origin
    assert len(expected.elem) == len(gnmi_path.elem)

    for exp_elem, actual_elem in zip(expected.elem, gnmi_path.elem):
        assert exp_elem.name == actual_elem.name
        assert len(exp_elem.key) == len(actual_elem.key)
        for key in exp_elem.key:
            assert key in actual_elem.key
            assert exp_elem.key[key] == actual_elem.key[key]


@pytest.mark.parametrize(
    "path, expected",
    [
        (Path(elem=[]), None),
        (
            Path(elem=[PathElem(name="containers"), PathElem(name="container")]),
            "containers/container",
        ),
        (
            Path(elem=[PathElem(name="openconfig:containers"), PathElem(name="container")]),
            "openconfig:containers/container",
        ),
        (
            Path(elem=[PathElem(name="containers"), PathElem(name="container", key={"key": "value"})]),
            "containers/container[key=value]",
        ),
        (
            Path(
                elem=[
                    PathElem(name="containers"),
                    PathElem(name="container", key={"key": "value"}),
                    PathElem(name="config"),
                    PathElem(name="test"),
                ],
            ),
            "containers/container[key=value]/config/test",
        ),
        (
            Path(
                elem=[
                    PathElem(name="containers"),
                    PathElem(name="container", key={"key": "value"}),
                    PathElem(name="config"),
                    PathElem(name="ip", key={"ip": "2001:db8:0:2::/64"}),
                ],
            ),
            "containers/container[key=value]/config/ip[ip=2001:db8:0:2::/64]",
        ),
        (
            Path(
                elem=[
                    PathElem(name="containers"),
                    PathElem(name="container", key={"key1": "value1", "key2": ""}),
                    PathElem(name="test:config"),
                    PathElem(name="ip", key={"ip": "2001:db8:0:2::/64"}),
                ],
            ),
            "containers/container[key1=value1][key2=]/test:config/ip[ip=2001:db8:0:2::/64]",
        ),
    ],
)
def test_create_xpath(path: Path, expected: str) -> None:
    assert create_xpath(path) == expected


@pytest.mark.parametrize(
    "data, encoding, expected",
    [
        ([], 0, []),
        ([{"path": "containers/container", "data": {"test": "test"}}], 5, []),
        (
            [{"path": "containers/container", "data": {"test": "test"}}],
            0,
            [
                Update(
                    path=Path(origin="openconfig", elem=[PathElem(name="containers"), PathElem(name="container")]),
                    val=TypedValue(json_val=json.dumps({"test": "test"}).encode("utf-8")),
                )
            ],
        ),
        (
            [{"path": "containers/container", "data": {"test": "test"}}],
            1,
            [
                Update(
                    path=Path(origin="openconfig", elem=[PathElem(name="containers"), PathElem(name="container")]),
                    val=TypedValue(bytes_val=json.dumps({"test": "test"}).encode("utf-8")),
                )
            ],
        ),
        (
            [{"path": "containers/container", "data": {"test": "test"}}],
            2,
            [
                Update(
                    path=Path(origin="openconfig", elem=[PathElem(name="containers"), PathElem(name="container")]),
                    val=TypedValue(proto_bytes=json.dumps({"test": "test"}).encode("utf-8")),
                )
            ],
        ),
        (
            [{"path": "containers/container", "data": {"test": "test"}}],
            3,
            [
                Update(
                    path=Path(origin="openconfig", elem=[PathElem(name="containers"), PathElem(name="container")]),
                    val=TypedValue(ascii_val=json.dumps({"test": "test"}).encode("utf-8")),
                )
            ],
        ),
        (
            [{"path": "containers/container", "data": {"test": "test"}}],
            4,
            [
                Update(
                    path=Path(origin="openconfig", elem=[PathElem(name="containers"), PathElem(name="container")]),
                    val=TypedValue(json_ietf_val=json.dumps({"test": "test"}).encode("utf-8")),
                )
            ],
        ),
    ],
)
def test_create_update_obj(data: list, encoding: int, expected: list) -> None:
    assert create_update_obj(data, encoding) == expected


def _path(name: str) -> Path:
    return Path(elem=[PathElem(name=name)])


_any_value = Any(type_url="type.googleapis.com/test.Value", value=b"payload")
_leaflist_value = ScalarArray(element=[TypedValue(int_val=1), TypedValue(int_val=2)])


@pytest.mark.parametrize(
    "notification, expected",
    [
        (ProtoNotification(), Notification(timestamp=0)),
        (ProtoNotification(timestamp=123456789), Notification(timestamp=123456789)),
        (ProtoNotification(prefix=_path("interfaces")), Notification(timestamp=0, prefix="interfaces")),
        (ProtoNotification(atomic=True), Notification(timestamp=0, atomic=True)),
        (ProtoNotification(atomic=False), Notification(timestamp=0, atomic=None)),
        (
            ProtoNotification(delete=[_path("deleted"), _path("removed")]),
            Notification(timestamp=0, deletes=["deleted", "removed"]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("str"), val=TypedValue(string_val="hello"))]),
            Notification(timestamp=0, updates=[{"path": "str", "val": "hello"}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("int"), val=TypedValue(int_val=-42))]),
            Notification(timestamp=0, updates=[{"path": "int", "val": -42}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("bool"), val=TypedValue(bool_val=True))]),
            Notification(timestamp=0, updates=[{"path": "bool", "val": True}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("bytes"), val=TypedValue(bytes_val=b"raw-bytes"))]),
            Notification(timestamp=0, updates=[{"path": "bytes", "val": b"raw-bytes"}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("double"), val=TypedValue(double_val=1.5))]),
            Notification(timestamp=0, updates=[{"path": "double", "val": 1.5}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("leaflist"), val=TypedValue(leaflist_val=_leaflist_value))]),
            Notification(timestamp=0, updates=[{"path": "leaflist", "val": _leaflist_value}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("any"), val=TypedValue(any_val=_any_value))]),
            Notification(timestamp=0, updates=[{"path": "any", "val": _any_value}]),
        ),
        (
            ProtoNotification(
                update=[Update(path=_path("json"), val=TypedValue(json_val=json.dumps({"a": 1}).encode("utf-8")))]
            ),
            Notification(timestamp=0, updates=[{"path": "json", "val": {"a": 1}}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("json_raw"), val=TypedValue(json_val=b"not-json"))]),
            Notification(timestamp=0, updates=[{"path": "json_raw", "val": b"not-json"}]),
        ),
        (
            ProtoNotification(
                update=[
                    Update(path=_path("json_ietf"), val=TypedValue(json_ietf_val=json.dumps([1, 2]).encode("utf-8")))
                ]
            ),
            Notification(timestamp=0, updates=[{"path": "json_ietf", "val": [1, 2]}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("ascii"), val=TypedValue(ascii_val="plain text"))]),
            Notification(timestamp=0, updates=[{"path": "ascii", "val": "plain text"}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("proto"), val=TypedValue(proto_bytes=b"encoded"))]),
            Notification(timestamp=0, updates=[{"path": "proto", "val": b"encoded"}]),
        ),
        (
            ProtoNotification(update=[Update(path=_path("dup"), val=TypedValue(int_val=1), duplicates=3)]),
            Notification(timestamp=0, updates=[{"path": "dup", "val": 1, "duplicates": 3}]),
        ),
        (
            ProtoNotification(
                timestamp=42,
                prefix=_path("interfaces"),
                atomic=True,
                update=[Update(path=_path("state"), val=TypedValue(string_val="up"))],
                delete=[_path("removed")],
            ),
            Notification(
                timestamp=42,
                prefix="interfaces",
                atomic=True,
                updates=[{"path": "state", "val": "up"}],
                deletes=["removed"],
            ),
        ),
    ],
)
def test_parse_notification(notification: ProtoNotification, expected: Notification) -> None:
    assert parse_notification(notification) == expected
