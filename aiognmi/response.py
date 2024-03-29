from datetime import datetime
from typing import Any

from grpc.aio import AioRpcError


class Response:
    finish_time: datetime | None = None
    elapsed_time: float | None = None
    result: dict | str | None = None
    failed: bool = True
    debug_error_string: str | None = None

    def __init__(self, target: str) -> None:
        """
        Response object

        Args:
            host: host that was operated on
        """
        self.target = target
        self.start_time = datetime.now()

    def set_elapsed_time(self) -> None:
        """
        Set the time spent on completion
        """
        self.finish_time = datetime.now()
        self.elapsed_time = (self.finish_time - self.start_time).total_seconds()

    def record_response(self, raw_result: Any, result: dict, failed: bool = False) -> None:
        """
        Record gNMI results and elapsed time

        Args:
            raw_result: raw gNMI result
            result: parsed gNMI result
            failed: status of the gNMI result
        """
        self.set_elapsed_time()
        self.raw_result = raw_result
        self.result = result
        self.failed = failed

    def record_error(self, error: AioRpcError) -> None:
        """
        Record AioRpcError and elapsed time

        Args:
            error: AioRpcError object
        """
        self.set_elapsed_time()
        self.raw_result = error
        self.result = error.details()
        self.failed = True
        self.debug_error_string = error.debug_error_string()
