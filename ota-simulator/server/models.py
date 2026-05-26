from pydantic import BaseModel
from enum import Enum
from typing import Optional


class PartitionStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"
    EMPTY = "empty"


class PartitionInfo(BaseModel):
    version: str = "0.0.0"
    status: PartitionStatus = PartitionStatus.EMPTY


class DeviceState(BaseModel):
    active_partition: str = "A"
    partitions: dict[str, PartitionInfo] = {
        "A": PartitionInfo(version="1.0.0", status=PartitionStatus.OK),
        "B": PartitionInfo(),
    }
    upgrade_history: list[dict] = []


class FirmwareListItem(BaseModel):
    version: str
    path: str
    size_kb: float


class DownloadRequest(BaseModel):
    version: str


class UpgradeRequest(BaseModel):
    version: str
    simulate_failure: bool = False


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


class VerifyResult(BaseModel):
    success: bool
    algorithm: str
    expected: str
    actual: str
    match: bool
