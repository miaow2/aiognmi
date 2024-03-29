import json

import pytest

from aiognmi.proto.gnmi.gnmi_pb2 import Path, PathElem, TypedValue, Update
from aiognmi.utils import create_gnmi_path, create_update_obj, create_xpath, get_origin, parse_key_value, split_path


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
