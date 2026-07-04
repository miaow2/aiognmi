---
name: update-gnmi-protos
description: Update this repository's vendored OpenConfig gNMI protobuf files and generated Python gRPC modules to a user-specified gNMI tag or version. Use when Codex is asked to refresh aiognmi/proto from openconfig/gnmi, regenerate gnmi_pb2.py or gnmi_pb2_grpc.py, support a newer gNMI release, or verify the upstream gnmi_service option after a proto update.
---

# Update gNMI Protos

## Required Input

Require the target OpenConfig gNMI version from the user before making changes.
Accept either `0.14.1` or `v0.14.1`; use the matching GitHub tag `vX.Y.Z`.

If the user does not provide a version, ask for it.

## Workflow

1. Inspect the worktree before editing:
   - `git status --short`
   - `rg -n "gnmi_service|gNMI release|protobuf==|grpcio-tools" README.md pyproject.toml aiognmi/proto tests`
2. Run the helper script from the repository root:
   - `.venv/bin/python .agents/skills/update-gnmi-protos/scripts/update_gnmi_protos.py <version>`
   - If `.venv` is unavailable, use the active project Python that has `grpcio-tools` installed.
   - If `grpcio-tools` is missing, install the repo's dev dependencies first.
3. Review generated changes:
   - `git diff -- aiognmi/proto`
   - Confirm generated imports use `aiognmi.proto.gnmi` and `aiognmi.proto.gnmi_ext`, not top-level `gnmi` or `gnmi_ext`.
4. Update project metadata when required:
   - If regenerated files validate a newer protobuf runtime, update `protobuf==...` in `pyproject.toml`.
   - Keep `grpcio` and `grpcio-tools` aligned when the generated gRPC files require a specific minimum version.
   - Add `grpcio-tools==...` to dev dependencies if it is not already present.
5. Update docs and tests:
   - Update README wording to name the vendored OpenConfig gNMI release.
   - Do not change the reported gNMI service version unless upstream changed `option (gnmi_service)`.
   - Add focused tests for newly available messages, enums, or extension fields.
6. Validate:
   - `uv run --extra dev ruff format .`
   - `uv run --extra dev ruff check .`
   - `uv run --extra test pytest`
   - If the sandboxed home cache is read-only, use `uv --cache-dir /tmp/uv-cache ...`.

## Important Details

- The upstream OpenConfig repository release tag and the core proto
  `option (gnmi_service)` are different concepts. For example, OpenConfig
  gNMI `v0.14.1` still declares `option (gnmi_service) = "0.10.0"`.
- Preserve this repo's local import path in `gnmi.proto`:
  `import "gnmi_ext/gnmi_ext.proto";`
- Do not hand-edit generated `*_pb2.py` or `*_pb2_grpc.py` beyond the package
  import rewrites needed after `grpc_tools.protoc` generation.
- Do not revert unrelated user changes in `pyproject.toml`, CI files, lockfiles,
  or other repo files.

## Helper Script

Use `scripts/update_gnmi_protos.py` for the fragile protobuf refresh steps. The
script intentionally does not update README, tests, or dependency pins; handle
those from the diff and generated runtime requirements.
