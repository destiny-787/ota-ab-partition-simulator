import json
import hashlib
import shutil
import time
import os
from pathlib import Path
from typing import AsyncIterator

from .models import DeviceState, PartitionInfo, PartitionStatus, FirmwareListItem, VerifyResult

BASE_DIR = Path(__file__).parent
FIRMWARE_DIR = BASE_DIR / "firmware"
STATE_FILE = FIRMWARE_DIR / "state.json"
REPO_DIR = FIRMWARE_DIR / "repo"


def _load_state() -> DeviceState:
    if STATE_FILE.exists():
        return DeviceState(**json.loads(STATE_FILE.read_text(encoding="utf-8")))
    state = DeviceState()
    _save_state(state)
    return state


def _save_state(state: DeviceState) -> None:
    STATE_FILE.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _inactive_partition(active: str) -> str:
    return "B" if active == "A" else "A"


def _compute_sha256(folder: Path) -> str:
    """Compute combined SHA256 of all files in a folder, excluding manifest.json."""
    h = hashlib.sha256()
    for f in sorted(folder.rglob("*")):
        if f.is_file() and f.name != "manifest.json":
            h.update(f.read_bytes())
    return h.hexdigest()


def _compute_md5(folder: Path) -> str:
    """Compute combined MD5 of all files in a folder, excluding manifest.json."""
    h = hashlib.md5()
    for f in sorted(folder.rglob("*")):
        if f.is_file() and f.name != "manifest.json":
            h.update(f.read_bytes())
    return h.hexdigest()


def get_state() -> DeviceState:
    return _load_state()


def list_firmware() -> list[FirmwareListItem]:
    items = []
    if REPO_DIR.exists():
        for d in sorted(REPO_DIR.iterdir()):
            if d.is_dir():
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                items.append(FirmwareListItem(
                    version=d.name,
                    path=str(d),
                    size_kb=round(size / 1024, 1),
                ))
    return items


async def download_firmware(version: str, progress_cb=None) -> Path:
    """Copy firmware from repo to inactive partition (simulates download)."""
    state = _load_state()
    src = REPO_DIR / version
    if not src.exists():
        raise FileNotFoundError(f"Firmware version {version} not found in repo")

    target = _inactive_partition(state.active_partition)
    dst = FIRMWARE_DIR / f"partition_{target.lower()}"
    manifest_dst = dst / "manifest.json"

    # Simulate download with progress
    files = list(src.rglob("*"))
    total = len([f for f in files if f.is_file()])
    for i, f in enumerate(sorted(files)):
        if f.is_file():
            rel = f.relative_to(src)
            target_file = dst / rel
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target_file)
            if progress_cb:
                pct = round((i + 1) / max(total, 1) * 100)
                await progress_cb("downloading", pct)
            time.sleep(0.3)  # simulate network latency

    # Write manifest with checksums
    sha256 = _compute_sha256(dst)
    md5 = _compute_md5(dst)
    manifest = {"version": version, "sha256": sha256, "md5": md5}
    manifest_dst.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Update partition version in state
    state.partitions[target].version = version
    state.partitions[target].status = PartitionStatus.OK
    _save_state(state)

    return dst


def verify_firmware() -> VerifyResult:
    """Verify firmware in inactive partition against manifest."""
    state = _load_state()
    target = _inactive_partition(state.active_partition)
    dst = FIRMWARE_DIR / f"partition_{target.lower()}"
    manifest_file = dst / "manifest.json"

    if not manifest_file.exists():
        return VerifyResult(
            success=False, algorithm="sha256",
            expected="N/A", actual="N/A", match=False,
        )

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected_sha = manifest["sha256"]
    actual_sha = _compute_sha256(dst)
    expected_md5 = manifest["md5"]
    actual_md5 = _compute_md5(dst)

    sha_match = expected_sha == actual_sha
    md5_match = expected_md5 == actual_md5

    return VerifyResult(
        success=sha_match and md5_match,
        algorithm="SHA256+MD5",
        expected=expected_sha[:16] + "...",
        actual=actual_sha[:16] + "...",
        match=sha_match and md5_match,
    )


async def perform_upgrade(simulate_failure: bool = False, progress_cb=None) -> dict:
    """Execute the upgrade: verify -> write -> switch. Auto-rollback on failure."""
    state = _load_state()
    old_partition = state.active_partition
    new_partition = _inactive_partition(old_partition)
    old_version = state.partitions[old_partition].version

    # Stage 1: Verify
    if progress_cb:
        await progress_cb("verifying", 0)
    vr = verify_firmware()
    if not vr.match:
        return {"success": False, "message": f"Verification failed: checksum mismatch", "rolled_back": False}

    # Stage 2: Simulate write
    if progress_cb:
        for pct in [25, 50, 75, 100]:
            await progress_cb("writing", pct)
            time.sleep(0.3)

    if simulate_failure:
        state.partitions[new_partition].status = PartitionStatus.FAILED
        _save_state(state)
        if progress_cb:
            await progress_cb("failed", 0)
        # Auto rollback
        state = _load_state()
        state.active_partition = old_partition
        state.partitions[new_partition].status = PartitionStatus.FAILED
        state.upgrade_history.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "from_version": old_version,
            "to_version": state.partitions[new_partition].version or "unknown",
            "result": "failed",
            "rolled_back": True,
        })
        _save_state(state)
        return {"success": False, "message": f"Write to partition {new_partition} failed, auto-rolled back to {old_partition}", "rolled_back": True}

    # Stage 3: Switch partitions
    if progress_cb:
        await progress_cb("switching", 0)
    time.sleep(0.5)

    new_version = state.partitions[new_partition].version
    state.active_partition = new_partition
    state.partitions[new_partition].status = PartitionStatus.OK
    state.upgrade_history.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "from_version": old_version,
        "to_version": new_version,
        "result": "success",
        "rolled_back": False,
    })
    _save_state(state)

    if progress_cb:
        await progress_cb("complete", 100)

    return {
        "success": True,
        "message": f"Upgrade complete. Active partition: {new_partition}, version: {new_version}",
        "old_partition": old_partition,
        "new_partition": new_partition,
        "new_version": new_version,
        "rolled_back": False,
    }


def perform_rollback() -> dict:
    """Manual rollback to the inactive partition."""
    state = _load_state()
    old = state.active_partition
    new = _inactive_partition(old)

    if state.partitions[new].status == PartitionStatus.EMPTY:
        return {"success": False, "message": f"Partition {new} is empty, cannot rollback"}

    state.active_partition = new
    state.upgrade_history.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "from_version": state.partitions[old].version,
        "to_version": state.partitions[new].version,
        "result": "rollback",
        "rolled_back": True,
    })
    _save_state(state)

    return {
        "success": True,
        "message": f"Rollback complete. Active partition: {new}, version: {state.partitions[new].version}",
        "active_partition": new,
    }
