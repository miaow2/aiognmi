import json
import re
from typing import Any

from aiognmi.proto.gnmi.gnmi_pb2 import Path, TypedValue, Update


def get_origin(path: str) -> tuple[str, str | None]:
    """
    Getting origin from path, e.g. from path "yang-module:container/container[key=value]" origin will be "yang-module"

    Args:
        path: string gNMI path

    Returns:
        tuple: path without origin and origin
    """
    origin = None
    origin_split = path.split("/", 1)
    if ":" in origin_split[0]:
        origin, elem = origin_split[0].split(":", 1)
        path = f"{elem}/{origin_split[1]}" if len(origin_split) > 1 else elem

    return path, origin


def split_path(path: str) -> list[str]:
    """
    Split path into elements by '/', e.g. path "container/container[key=value]" will be separated into
    ['container', 'container[key=value]']

    Args:
        path: string gNMI path

    Returns:
        list: list of paths elements
    """
    elements = []
    inside_brackets = False
    begin = 0
    end = 0

    while end < len(path):
        match path[end]:
            case "/":
                if inside_brackets:
                    end += 1
                else:
                    if end > begin:
                        elements.append(path[begin:end])
                    end += 1
                    begin = end
            case "[":
                if (end == 0 or path[end - 1] != "\\") and inside_brackets is False:
                    inside_brackets = True
                end += 1
            case "]":
                if (end == 0 or path[end - 1] != "\\") and inside_brackets:
                    inside_brackets = False
                end += 1
            case _:
                end += 1
        if end == len(path) and path[end - 1] != "/":
            elements.append(path[begin:end])

    return elements


def parse_key_value(elem: str) -> dict:
    """
    Parse [k1=v1][k2=v2] into {"k1": "v1", "k2": "v2"}

    Args:
        elem: element of gNMI path

    Returns:
        dict: dictionary with key-values
    """
    keys = {}
    for key_value in re.findall(r"\[(.+?)\]", elem):
        key, value = key_value.split("=")
        keys[key] = value

    return keys


def create_gnmi_path(path: str | None, target: str | None = None) -> Path:
    """
    Create gNMI Path from xpath

    Args:
        path: string gNMI path
        target: The name of the target

    Returns:
        Path: gNMI Path object
    """
    gnmi_path = Path()
    gnmi_path.origin = "openconfig"
    if target:
        gnmi_path.target = target
    if path:
        path += "/"
        path, origin = get_origin(path)
        if origin:
            gnmi_path.origin = origin

        elements = split_path(path)

        for elem in elements:
            if match := re.match(r"(?P<name>.+?)(?P<keys>\[.+\])", elem):
                keys = parse_key_value(match["keys"])
                gnmi_path.elem.add(name=match["name"], key=keys)
            else:
                gnmi_path.elem.add(name=elem)

    return gnmi_path


def create_xpath(path: Path | None) -> str | None:
    """
    Create xpath from gNMI Path

    Args:
        path: gNMI Path object

    Returns:
        Path: string gNMI path
    """
    result = None
    if path and path.elem:
        parts = []
        for elem in path.elem:
            temp_path = ""
            if elem.name:
                temp_path += elem.name

            if elem.key:
                for key, value in sorted(elem.key.items()):
                    temp_path += f"[{key}={value}]"

            parts.append(temp_path)

        result = "/".join(parts)

    return result


def parse_typed_value(value: TypedValue) -> Any:
    """
    Get value from TypedValue

    Args:
        value: TypedValue object

    Returns:
        Any: value from TypedValue
    """
    if value.HasField("string_val"):
        return value.string_val
    elif value.HasField("int_val"):
        return value.int_val
    elif value.HasField("bool_val"):
        return value.bool_val
    elif value.HasField("bytes_val"):
        return value.bytes_val
    elif value.HasField("double_val"):
        return value.double_val
    elif value.HasField("leaflist_val"):
        return value.leaflist_val
    elif value.HasField("any_val"):
        return value.any_val
    elif value.HasField("json_val"):
        try:
            return json.loads(value.json_val)
        except json.decoder.JSONDecodeError:
            return value.json_val
    elif value.HasField("json_ietf_val"):
        try:
            return json.loads(value.json_ietf_val)
        except json.decoder.JSONDecodeError:
            return value.json_ietf_val
    elif value.HasField("ascii_val"):
        return value.ascii_val
    elif value.HasField("proto_bytes"):
        return value.proto_bytes


def create_update_obj(data: list[dict], encoding: int) -> list[Update]:
    """
    Create Update message object

    Args:
        data: list of dicts where keys are: `path` stores xpath string, `data` is a dict with values to send to device

    Returns:
        list: list of Update objects
    """
    result = []
    for msg in data:
        value = json.dumps(msg["data"]).encode("utf-8")
        if encoding == 0:
            result.append(Update(path=create_gnmi_path(msg["path"]), val=TypedValue(json_val=value)))
        elif encoding == 1:
            result.append(Update(path=create_gnmi_path(msg["path"]), val=TypedValue(bytes_val=value)))
        elif encoding == 2:
            result.append(Update(path=create_gnmi_path(msg["path"]), val=TypedValue(proto_bytes=value)))
        elif encoding == 3:
            result.append(Update(path=create_gnmi_path(msg["path"]), val=TypedValue(ascii_val=value)))
        elif encoding == 4:
            result.append(Update(path=create_gnmi_path(msg["path"]), val=TypedValue(json_ietf_val=value)))

    return result
