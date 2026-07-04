#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


RAW_BASE_URL = "https://raw.githubusercontent.com/openconfig/gnmi/{tag}/proto/{path}"
PROTO_FILES = {
    "gnmi/gnmi.proto": Path("aiognmi/proto/gnmi/gnmi.proto"),
    "gnmi_ext/gnmi_ext.proto": Path("aiognmi/proto/gnmi_ext/gnmi_ext.proto"),
}
UPSTREAM_GNMI_EXT_IMPORT = 'import "github.com/openconfig/gnmi/proto/gnmi_ext/gnmi_ext.proto";'
LOCAL_GNMI_EXT_IMPORT = 'import "gnmi_ext/gnmi_ext.proto";'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update vendored OpenConfig gNMI protos and generated Python stubs.")
    parser.add_argument("version", help='OpenConfig gNMI version or tag, for example "0.14.1" or "v0.14.1".')
    parser.add_argument(
        "--repo-root",
        default=Path.cwd(),
        type=Path,
        help="Repository root. Defaults to the current working directory.",
    )
    return parser.parse_args()


def normalize_tag(version: str) -> str:
    version = version.strip()
    if not version:
        raise SystemExit("version is required, for example 0.14.1 or v0.14.1")
    return version if version.startswith("v") else f"v{version}"


def download_text(tag: str, proto_path: str) -> str:
    url = RAW_BASE_URL.format(tag=tag, path=proto_path)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"failed to download {url}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"failed to download {url}: {exc.reason}") from exc


def write_proto_files(repo_root: Path, tag: str) -> None:
    downloaded = {proto_path: download_text(tag, proto_path) for proto_path in PROTO_FILES}

    gnmi_proto = downloaded["gnmi/gnmi.proto"]
    if UPSTREAM_GNMI_EXT_IMPORT in gnmi_proto:
        gnmi_proto = gnmi_proto.replace(UPSTREAM_GNMI_EXT_IMPORT, LOCAL_GNMI_EXT_IMPORT)
    elif LOCAL_GNMI_EXT_IMPORT not in gnmi_proto:
        raise SystemExit("gnmi.proto does not contain a recognized gnmi_ext import path")
    downloaded["gnmi/gnmi.proto"] = gnmi_proto

    for proto_path, relative_target in PROTO_FILES.items():
        target = repo_root / relative_target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(downloaded[proto_path], encoding="utf-8")
        if not downloaded[proto_path].endswith("\n"):
            with target.open("a", encoding="utf-8") as file_obj:
                file_obj.write("\n")


def run_protoc(repo_root: Path) -> None:
    proto_root = repo_root / "aiognmi/proto"
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        "-I",
        str(proto_root),
        "--python_out",
        str(proto_root),
        "--grpc_python_out",
        str(proto_root),
        str(proto_root / "gnmi_ext/gnmi_ext.proto"),
        str(proto_root / "gnmi/gnmi.proto"),
    ]
    subprocess.run(cmd, cwd=repo_root, check=True)


def replace_or_verify(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")
        return
    if new in text:
        return
    raise SystemExit(f"{path} did not contain expected generated import: {old!r}")


def patch_generated_imports(repo_root: Path) -> None:
    replace_or_verify(
        repo_root / "aiognmi/proto/gnmi/gnmi_pb2.py",
        "from gnmi_ext import gnmi_ext_pb2 as gnmi__ext_dot_gnmi__ext__pb2",
        "from aiognmi.proto.gnmi_ext import gnmi_ext_pb2 as gnmi__ext_dot_gnmi__ext__pb2",
    )
    replace_or_verify(
        repo_root / "aiognmi/proto/gnmi/gnmi_pb2_grpc.py",
        "from gnmi import gnmi_pb2 as gnmi_dot_gnmi__pb2",
        "from aiognmi.proto.gnmi import gnmi_pb2 as gnmi_dot_gnmi__pb2",
    )


def verify_imports(repo_root: Path) -> str:
    cmd = [
        sys.executable,
        "-c",
        (
            "from aiognmi.proto.gnmi import gnmi_pb2; "
            "from aiognmi.proto.gnmi_ext import gnmi_ext_pb2; "
            "print(gnmi_pb2.DESCRIPTOR.GetOptions().Extensions[gnmi_pb2.gnmi_service]); "
            "print(gnmi_ext_pb2.DESCRIPTOR.name)"
        ),
    ]
    result = subprocess.run(cmd, cwd=repo_root, check=True, stdout=subprocess.PIPE, text=True)
    lines = result.stdout.splitlines()
    if len(lines) != 2 or lines[1] != "gnmi_ext/gnmi_ext.proto":
        raise SystemExit(f"generated import verification returned unexpected output: {result.stdout!r}")
    return lines[0]


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    tag = normalize_tag(args.version)

    if not (repo_root / "aiognmi/proto").is_dir():
        raise SystemExit(f"{repo_root} does not look like the aiognmi repository root")

    write_proto_files(repo_root, tag)
    run_protoc(repo_root)
    patch_generated_imports(repo_root)
    service_version = verify_imports(repo_root)

    print(f"Updated vendored gNMI protobuf files from OpenConfig {tag}.")
    print(f"Verified generated modules import successfully; upstream gnmi_service is {service_version}.")
    print("Review README, pyproject.toml dependency pins, and tests before committing.")


if __name__ == "__main__":
    main()
