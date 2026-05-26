from fastapi import APIRouter, HTTPException
from .models import (
    ApiResponse, DownloadRequest, UpgradeRequest, VerifyResult,
    FirmwareListItem,
)
from . import ota_core

router = APIRouter(prefix="/api")


@router.get("/version")
def get_version() -> ApiResponse:
    state = ota_core.get_state()
    return ApiResponse(
        success=True, message="ok",
        data={
            "active_partition": state.active_partition,
            "partitions": {
                k: v.model_dump() for k, v in state.partitions.items()
            },
            "upgrade_history": state.upgrade_history[-5:],
        },
    )


@router.get("/firmware")
def list_firmware() -> ApiResponse:
    items = ota_core.list_firmware()
    return ApiResponse(
        success=True, message=f"{len(items)} firmware versions available",
        data={"firmware": [item.model_dump() for item in items]},
    )


@router.post("/download")
def download_firmware(req: DownloadRequest) -> ApiResponse:
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ota_core.download_firmware(req.version))
        loop.close()
        return ApiResponse(success=True, message=f"Firmware {req.version} downloaded to inactive partition")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/verify")
def verify_firmware() -> VerifyResult:
    return ota_core.verify_firmware()


@router.post("/upgrade")
def upgrade(req: UpgradeRequest) -> ApiResponse:
    import asyncio
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(
        ota_core.perform_upgrade(simulate_failure=req.simulate_failure)
    )
    loop.close()
    return ApiResponse(
        success=result["success"],
        message=result["message"],
        data=result,
    )


@router.post("/rollback")
def rollback() -> ApiResponse:
    result = ota_core.perform_rollback()
    return ApiResponse(
        success=result["success"],
        message=result["message"],
        data=result,
    )
