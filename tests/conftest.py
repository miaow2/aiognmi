from collections.abc import Callable
from typing import Any

import pytest

from aiognmi import AsyncgNMIClient


@pytest.fixture
def make_client() -> Callable[..., AsyncgNMIClient]:
    def _make_client(**kwargs: Any) -> AsyncgNMIClient:
        return AsyncgNMIClient(
            host="127.0.0.1",
            port=57400,
            username="user",
            password="password",
            **kwargs,
        )

    return _make_client
