import asyncio
import logging
import ssl
from pathlib import Path
from types import TracebackType

from cryptography import x509
from cryptography.x509.oid import NameOID
from google.protobuf.duration_pb2 import Duration
from grpc import ssl_channel_credentials
from grpc.aio import AioRpcError, insecure_channel, secure_channel

from aiognmi.models import CapabilitiesResult, GetResult, Notification, SetResult
from aiognmi.proto.gnmi.gnmi_pb2 import (
    CapabilityRequest,
    CapabilityResponse,
    Encoding,
    GetRequest,
    GetResponse,
    SetRequest,
    SetResponse,
)
from aiognmi.proto.gnmi.gnmi_pb2_grpc import gNMIStub
from aiognmi.proto.gnmi_ext.gnmi_ext_pb2 import (
    Commit,
    CommitCancel,
    CommitConfirm,
    CommitRequest,
    CommitSetRollbackDuration,
    Depth,
    Extension,
)
from aiognmi.response import Response
from aiognmi.utils import create_gnmi_path, create_update_obj, create_xpath, parse_typed_value

logger = logging.getLogger(__name__)


async def _read_file(path: str) -> bytes:
    """
    Read a file's contents asynchronously without blocking the event loop

    Args:
        path: path to the file to read

    Returns:
        bytes: contents of the file
    """
    return await asyncio.to_thread(Path(path).read_bytes)


def _get_cert_hostname(cert_pem: bytes) -> str | None:
    """
    Extract an identity to use for hostname verification override from a PEM-encoded certificate

    Priority order: first DNS name in the SubjectAlternativeName extension, then first IP address
    in the SubjectAlternativeName extension, then the subject Common Name.

    Args:
        cert_pem: PEM-encoded certificate bytes

    Returns:
        str | None: the extracted identity, or None if none could be found
    """
    cert = x509.load_pem_x509_certificate(cert_pem)

    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        san = None

    if san is not None:
        dns_names = san.get_values_for_type(x509.DNSName)
        if dns_names:
            return dns_names[0]

        ip_addresses = san.get_values_for_type(x509.IPAddress)
        if ip_addresses:
            return str(ip_addresses[0])

    common_names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if common_names:
        return common_names[0].value

    return None


def _validate_positive_seconds(name: str, value: int) -> None:
    """
    Validate that a duration argument is a positive integer number of seconds

    Args:
        name: argument name used in the error message
        value: value to validate

    Raises:
        ValueError: if the value is not a positive integer
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _build_commit_extension(
    commit_id: str | None,
    commit_rollback_duration: int | None,
    commit_confirm: bool,
    commit_cancel: bool,
    commit_set_rollback_duration: int | None,
) -> Extension | None:
    """
    Build a commit-confirmed Extension from the selected commit action

    Args:
        commit_id: client-provided identifier for a commit-confirmed action
        commit_rollback_duration: positive rollback timeout in seconds; starts a commit-confirmed operation
        commit_confirm: confirm the active commit identified by commit_id
        commit_cancel: cancel the active commit identified by commit_id
        commit_set_rollback_duration: positive timeout in seconds to set on the active commit

    Returns:
        Extension | None: the commit extension, or None when no commit options are used

    Raises:
        ValueError: if commit_id is missing, no single action is selected, or a duration is invalid
    """
    commit_actions = [
        commit_rollback_duration is not None,
        bool(commit_confirm),
        bool(commit_cancel),
        commit_set_rollback_duration is not None,
    ]
    if commit_id is None and not any(commit_actions):
        return None

    if not isinstance(commit_id, str) or not commit_id:
        raise ValueError("commit_id is required for commit-confirmed actions")
    if sum(commit_actions) != 1:
        raise ValueError("exactly one commit-confirmed action must be selected")

    if commit_rollback_duration is not None:
        _validate_positive_seconds("commit_rollback_duration", commit_rollback_duration)
        commit = Commit(
            id=commit_id,
            commit=CommitRequest(rollback_duration=Duration(seconds=commit_rollback_duration)),
        )
    elif commit_confirm:
        commit = Commit(id=commit_id, confirm=CommitConfirm())
    elif commit_cancel:
        commit = Commit(id=commit_id, cancel=CommitCancel())
    else:
        _validate_positive_seconds("commit_set_rollback_duration", commit_set_rollback_duration)
        commit = Commit(
            id=commit_id,
            set_rollback_duration=CommitSetRollbackDuration(
                rollback_duration=Duration(seconds=commit_set_rollback_duration)
            ),
        )

    return Extension(commit=commit)


class AsyncgNMIClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        insecure: bool = False,
        verify: bool = True,
        # gnmi_timeout: int = 5,
        grpc_options: list | None = None,
        # token: str = None,
        # no_qos_marking: bool = False,
        path_root_cert: str | None = None,
        path_private_key: str | None = None,
        path_cert_chain: str | None = None,
        **kwargs,
    ) -> None:
        """
        A main client class to interact with the devices

        Args:
            host: host ip/name to connect to
            port: port to connect to
            username: username for authentication
            password: password for authentication
            insecure: use SSl certificate for connection or not
            verify: verify the server certificate; when False, the target's certificate is fetched and
              trusted instead (trust-on-first-use)
            grpc_options: options for gRPC connection
            path_root_cert: path to root certificate for SSL authentication
            path_private_key: path to private key for SSL authentication
            path_cert_chain: path to certificate chain for SSL authentication
        """
        self.host = host
        self.port = port
        self.credentials = [("username", username), ("password", password)]
        self.insecure = insecure
        self.verify = verify
        self.grpc_options = grpc_options or []
        self.default_encoding = "JSON"
        self.path_root_cert = path_root_cert
        self.path_private_key = path_private_key
        self.path_cert_chain = path_cert_chain

    @property
    def target(self) -> str:
        """
        Set target
        """
        return f"{self.host}:{self.port}"

    def get_grpc_options(self) -> list:
        """
        Get gRPC options for channel
        """
        return self.credentials + self.grpc_options

    async def __aenter__(self) -> "AsyncgNMIClient":
        """
        Enter method for context manager
        """
        await self.connect()
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """
        Exit method to cleanup for context manager

        Args:
            exception_type: exception type being raised
            exception_value: message from exception being raised
            traceback: traceback from exception being raised
        """
        await self.close()

    async def connect(self) -> None:
        """
        Open channel for target
        """
        if self.insecure:
            self.channel = insecure_channel(target=self.target, options=self.get_grpc_options())
        else:
            root_cert = await _read_file(self.path_root_cert) if self.path_root_cert else None
            private_key = await _read_file(self.path_private_key) if self.path_private_key else None
            cert_chain = await _read_file(self.path_cert_chain) if self.path_cert_chain else None

            options = self.get_grpc_options()

            if not self.verify:
                logger.warning(
                    f"Server certificate verification is disabled for {self.host}, "
                    "the target's certificate will be fetched and trusted (trust-on-first-use)"
                )
                fetched_pem = await asyncio.to_thread(ssl.get_server_certificate, (self.host, self.port))
                fetched = fetched_pem.encode("utf-8")

                if root_cert is None:
                    root_cert = fetched

                hostname = _get_cert_hostname(fetched)
                if hostname is None:
                    logger.warning(f"Could not extract an identity from the fetched certificate for {self.host}")
                else:
                    options = options + [
                        ("grpc.ssl_target_name_override", hostname),
                        ("grpc.default_authority", hostname),
                    ]

            credentials = ssl_channel_credentials(
                root_certificates=root_cert, private_key=private_key, certificate_chain=cert_chain
            )
            self.channel = secure_channel(target=self.target, credentials=credentials, options=options)

        self.stub = gNMIStub(self.channel)

    async def close(self) -> None:
        """
        CLosing channel
        """
        await self.channel.close()

    def get_encoding(self, encoding: str | None) -> int:
        if encoding is None:
            return Encoding.Value(self.default_encoding)

        try:
            encoding = Encoding.Value(encoding.upper())
        except ValueError:
            logger.warning(f"Encoding {encoding} is not supported in gNMI request, setting {self.default_encoding}")
            encoding = Encoding.Value(self.default_encoding)

        return encoding

    def _pre_get_capabilities(self) -> Response:
        """
        Create Response object

        Returns:
            Response: new response object
        """
        logger.info(f"get_capabilities for {self.host} is requested")

        return Response(target=self.target)

    def _post_get_capabilities(self, raw_response: CapabilityResponse, response: Response) -> Response:
        """
        Parse gNMI capabilities response

        Args:
            raw_response: gNMI response with capabilities from device
            response: response object

        Returns:
            Response: response object with results
        """
        result = CapabilitiesResult()
        if raw_response.supported_models:
            result.supported_models = [
                {
                    "name": model.name,
                    "organization": model.organization,
                    "version": model.version,
                }
                for model in raw_response.supported_models
            ]

        if raw_response.supported_encodings:
            encodings = {value: key for key, value in Encoding.items()}
            for item in raw_response.supported_encodings:
                if encoding := encodings.get(item):
                    result.supported_encodings.append(encoding)

        if raw_response.gNMI_version:
            result.gNMI_version = raw_response.gNMI_version

        response.record_response(raw_response, result.dict())

        return response

    def _pre_get(self) -> Response:
        """
        Create Response object

        Returns:
            Response: new response object
        """
        logger.info(f"get for {self.host} is requested")

        return Response(target=self.target)

    def _post_get(self, raw_response: GetResponse, response: Response) -> Response:
        """
        Parse gNMI get response

        Args:
            raw_response: gNMI get response from device
            response: response object

        Returns:
            Response: response object with results
        """
        result = GetResult()
        if raw_response.notification:
            for notification in raw_response.notification:
                note = Notification(
                    **{
                        "timestamp": notification.timestamp if notification.timestamp else 0,
                        "prefix": create_xpath(notification.prefix) if notification.prefix else None,
                        "atomic": notification.atomic if notification.atomic else None,
                    }
                )
                if notification.update:
                    for msg in notification.update:
                        data = {}
                        data["path"] = create_xpath(msg.path) if msg.path else None
                        if msg.val:
                            data["val"] = parse_typed_value(msg.val)
                        if msg.duplicates:
                            data["duplicates"] = msg.duplicates
                        note.updates.append(data)

                if notification.delete:
                    for path in notification.update:
                        if xpath := create_xpath(path):
                            note.deletes.append(xpath)

                result.notifications.append(note)

        response.record_response(raw_response, result.dict())

        return response

    def _pre_set(self) -> Response:
        """
        Create Response object

        Returns:
            Response: new response object
        """
        logger.info(f"set for {self.host} is requested")

        return Response(target=self.target)

    def _post_set(self, raw_response: SetResponse, response: Response) -> Response:
        """
        Parse gNMI set response

        Args:
            raw_response: gNMI set response from device
            response: response object

        Returns:
            Response: response object with results
        """
        result = SetResult(timestamp=raw_response.timestamp, prefix=create_xpath(raw_response.prefix))
        operation = {
            0: "INVALID",
            1: "DELETE",
            2: "REPLACE",
            3: "UPDATE",
            4: "UNION_REPLACE",
        }
        failed = False
        for resp in raw_response.response:
            if resp.op == 0:
                failed = True
            try:
                op = operation[resp.op]
            except KeyError:
                logger.error(f"Undefined operation {resp.op} in UpdateResult")
                op = "NOT DEFINED"
            result.update_results.append(
                {
                    "path": create_xpath(resp.path),
                    "op": op,
                }
            )
        response.record_response(raw_response, result.dict(), failed)

        return response

    async def get_capabilities(self) -> Response:
        """
        Getting gNMI capabilities from device

        Returns:
            Response: response object with results
        """
        response = self._pre_get_capabilities()
        try:
            gnmi_response = await self.stub.Capabilities(CapabilityRequest(), metadata=self.credentials)
        except AioRpcError as e:
            logger.error(e)
            response.record_error(e)
            return response

        return self._post_get_capabilities(gnmi_response, response)

    async def get(
        self,
        prefix: str | None = None,
        paths: list | None = None,
        data_type: str | None = None,
        encoding: str | None = None,
        target: str | None = None,
        extensions: list[Extension] | None = None,
        depth: int | None = None,
    ) -> Response:
        """
        Getting gNMI information from the specified paths

        Args:
            prefix: prefix for paths
            paths: list of paths
            data_type: type of data requested from the target. one of: ALL, CONFIG, STATE, OPERATIONAL (default "ALL")
            encoding: string one of ["json" "bytes" "proto" "ascii" "json_ietf"]. Case insensitive (default "json")
            target: the name of the target
            extensions: prebuilt gNMI Extension protobuf messages to include in the request
            depth: non-negative maximum subtree depth applied to every path in the request

        Returns:
            Response: response object with results
        """
        response = self._pre_get()

        prefix = create_gnmi_path(prefix, target or self.target)
        paths = [create_gnmi_path(p) for p in paths] if paths else []

        if data_type is None:
            data_type = GetRequest.DataType.Value("ALL")
        else:
            try:
                data_type = GetRequest.DataType.Value(data_type.upper())
            except ValueError:
                logger.warn(f"Data type {data_type} is not supported in GetRequest, setting ALL")
                data_type = GetRequest.DataType.Value("ALL")

        encoding = self.get_encoding(encoding)
        extensions = list(extensions or [])
        if depth is not None:
            if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
                raise ValueError("depth must be a non-negative integer")
            extensions.append(Extension(depth=Depth(level=depth)))

        request = GetRequest(prefix=prefix, path=paths, type=data_type, encoding=encoding, extension=extensions)
        try:
            gnmi_response = await self.stub.Get(request, metadata=self.credentials)
        except AioRpcError as e:
            logger.error(e)
            response.record_error(e)
            return response

        return self._post_get(gnmi_response, response)

    async def set(
        self,
        prefix: str | None = None,
        delete: list | None = None,
        replace: list | None = None,
        update: list | None = None,
        union_replace: list | None = None,
        encoding: str | None = None,
        target: str | None = None,
        extensions: list[Extension] | None = None,
        commit_id: str | None = None,
        commit_rollback_duration: int | None = None,
        commit_confirm: bool = False,
        commit_cancel: bool = False,
        commit_set_rollback_duration: int | None = None,
    ) -> Response:
        """
        Configuring device with set command

        Args:
            prefix: prefix for paths
            delete: list of paths to delete
            replace: list of dict where dicts store two keys: `path` path where to replace, `data` replace value
            update: list of dict where dicts store two keys: `path` path where to update, `data` update value
            union_replace: list of dict where dicts store two keys: `path` path, `data` update value, if union_replace
              is defined then a SetRequest will contain only union_replace operation
            encoding: string one of ["json" "bytes" "proto" "ascii" "json_ietf"], default "json"
            target: the name of the target
            extensions: prebuilt gNMI Extension protobuf messages to include in the request
            commit_id: client-provided identifier for a commit-confirmed action
            commit_rollback_duration: positive rollback timeout in seconds; starts a commit-confirmed operation
            commit_confirm: confirm the active commit identified by commit_id
            commit_cancel: cancel the active commit identified by commit_id
            commit_set_rollback_duration: positive timeout in seconds to set on the active commit

        Returns:
            Response: response object with results
        """
        delete_paths = []
        update_data = []
        replace_data = []
        union_replace_data = []
        response = self._pre_set()

        prefix = create_gnmi_path(prefix, target or self.target)
        encoding = self.get_encoding(encoding)

        if delete:
            delete_paths = [create_gnmi_path(p) for p in delete]
        if update:
            update_data = create_update_obj(update, encoding)
        if replace:
            replace_data = create_update_obj(replace, encoding)
        if union_replace:
            union_replace_data = create_update_obj(union_replace, encoding)

        extensions = list(extensions or [])
        commit_extension = _build_commit_extension(
            commit_id, commit_rollback_duration, commit_confirm, commit_cancel, commit_set_rollback_duration
        )
        if commit_extension is not None:
            extensions.append(commit_extension)

        if union_replace_data:
            request = SetRequest(prefix=prefix, union_replace=union_replace_data, extension=extensions)
        else:
            request = SetRequest(
                prefix=prefix,
                delete=delete_paths,
                update=update_data,
                replace=replace_data,
                extension=extensions,
            )
        try:
            gnmi_response = await self.stub.Set(request, metadata=self.credentials)
        except AioRpcError as e:
            logger.error(e)
            response.record_error(e)
            return response

        return self._post_set(gnmi_response, response)
