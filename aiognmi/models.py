from dataclasses import asdict, dataclass, field


class BaseDataClass:
    def dict(self) -> dict:
        return dict(asdict(self).items())


@dataclass
class CapabilitiesResult(BaseDataClass):
    supported_models: list[dict[str, str]] = field(default_factory=list)
    supported_encodings: list[str] = field(default_factory=list)
    gNMI_version: str | None = None


@dataclass
class Notification(BaseDataClass):
    timestamp: int | None = None
    prefix: str | None = None
    updates: list[dict] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)
    atomic: bool | None = None


@dataclass
class GetResult:
    notifications: list[Notification] = field(default_factory=list)

    def dict(self) -> dict:
        return {"notifications": [n.dict() for n in self.notifications]}


@dataclass
class SetResult(BaseDataClass):
    timestamp: int | None = None
    prefix: str | None = None
    update_results: list[dict] = field(default_factory=list)
