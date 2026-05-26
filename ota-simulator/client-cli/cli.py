#!/usr/bin/env python
"""OTA A/B Partition Upgrade Simulator - CLI Client"""

import sys
import json
import time
import asyncio
import argparse
from urllib.parse import urljoin

import requests
import websockets
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.layout import Layout

console = Console()
BASE_URL = "http://localhost:8000"


def api_url(path: str) -> str:
    return urljoin(BASE_URL, path)


def cmd_check():
    """Check current device version and partition status."""
    r = requests.get(api_url("/api/version"))
    data = r.json()
    if not data["success"]:
        console.print(f"[red]Error: {data['message']}[/red]")
        return

    d = data["data"]
    active = d["active_partition"]

    table = Table(title="Device Status")
    table.add_column("Partition", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Active", style="bold")

    for name, info in d["partitions"].items():
        marker = "◀── ACTIVE" if name == active else ""
        status_color = "green" if info["status"] == "ok" else "red" if info["status"] == "failed" else "dim"
        table.add_row(
            f"Partition {name}",
            info["version"],
            f"[{status_color}]{info['status']}[/{status_color}]",
            f"[bold blue]{marker}[/bold blue]",
        )

    console.print(table)

    if d.get("upgrade_history"):
        ht = Table(title="Recent Upgrade History")
        ht.add_column("Time")
        ht.add_column("From → To")
        ht.add_column("Result")
        for h in d["upgrade_history"]:
            result_color = "green" if h["result"] == "success" else "red"
            ht.add_row(
                h["timestamp"],
                f"{h['from_version']} → {h['to_version']}",
                f"[{result_color}]{h['result']}{' (rolled back)' if h.get('rolled_back') else ''}[/{result_color}]",
            )
        console.print(ht)


def cmd_firmware_list():
    """List available firmware versions."""
    r = requests.get(api_url("/api/firmware"))
    data = r.json()

    table = Table(title="Available Firmware")
    table.add_column("Version", style="cyan")
    table.add_column("Size", style="green")

    for fw in data["data"]["firmware"]:
        table.add_row(fw["version"], f"{fw['size_kb']} KB")

    console.print(table)


def cmd_download(version: str):
    """Download firmware to inactive partition."""
    console.print(f"[yellow]Downloading firmware {version}...[/yellow]")
    r = requests.post(api_url("/api/download"), json={"version": version})
    data = r.json()
    if data["success"]:
        console.print(f"[green]{data['message']}[/green]")
    else:
        console.print(f"[red]Error: {r.text}[/red]")


def cmd_verify():
    """Verify downloaded firmware checksums."""
    console.print("[yellow]Verifying firmware integrity...[/yellow]")
    r = requests.post(api_url("/api/verify"))
    data = r.json()
    if data["success"]:
        console.print(f"[green]Verification PASSED ({data['algorithm']})[/green]")
        console.print(f"  Expected: {data['expected']}")
        console.print(f"  Actual:   {data['actual']}")
    else:
        console.print(f"[red]Verification FAILED[/red]")
        console.print(f"  Expected: {data['expected']}")
        console.print(f"  Actual:   {data['actual']}")


async def _watch_progress():
    """Watch WebSocket for progress updates."""
    try:
        async with websockets.connect("ws://localhost:8000/ws/progress") as ws:
            while True:
                msg = json.loads(await ws.recv())
                if msg["event"] == "progress":
                    stage = msg.get("stage", "unknown")
                    pct = msg.get("percent", 0)
                    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                    console.print(f"\r  [{stage}] [{bar}] {pct}%", end="")
                elif msg["event"] == "complete":
                    console.print("\n[green]Upgrade complete![/green]")
                    break
                elif msg["event"] == "failed":
                    console.print("\n[red]Upgrade failed![/red]")
                    break
    except Exception:
        pass


def cmd_upgrade(version: str, simulate_failure: bool = False):
    """Execute OTA upgrade."""
    extra = " [bold red](SIMULATING FAILURE)[/bold red]" if simulate_failure else ""
    console.print(f"[yellow]Starting upgrade to {version}...{extra}[/yellow]")

    r = requests.post(api_url("/api/upgrade"), json={
        "version": version,
        "simulate_failure": simulate_failure,
    })
    data = r.json()

    if data["success"]:
        console.print(Panel.fit(
            f"[green]Upgrade successful![/green]\n"
            f"Active partition: {data['data']['new_partition']}\n"
            f"New version: {data['data']['new_version']}",
            title="OTA Upgrade Result",
        ))
    else:
        rolled = " (auto rollback triggered)" if data["data"].get("rolled_back") else ""
        console.print(Panel.fit(
            f"[red]Upgrade failed![/red]{rolled}\n"
            f"Reason: {data['message']}",
            title="OTA Upgrade Result",
        ))


def cmd_rollback():
    """Manual rollback to backup partition."""
    console.print("[yellow]Rolling back...[/yellow]")
    r = requests.post(api_url("/api/rollback"))
    data = r.json()
    if data["success"]:
        console.print(f"[green]{data['message']}[/green]")
    else:
        console.print(f"[red]{data['message']}[/red]")


def main():
    parser = argparse.ArgumentParser(description="OTA A/B Partition Upgrade CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="Check device version and partition status")
    sub.add_parser("firmware", help="List available firmware versions")

    dl = sub.add_parser("download", help="Download firmware")
    dl.add_argument("version", help="Firmware version to download")

    sub.add_parser("verify", help="Verify firmware checksums")

    up = sub.add_parser("upgrade", help="Execute OTA upgrade")
    up.add_argument("version", help="Target firmware version")
    up.add_argument("--fail", action="store_true", help="Simulate upgrade failure")

    sub.add_parser("rollback", help="Manual rollback to backup partition")

    args = parser.parse_args()

    if args.command == "check":
        cmd_check()
    elif args.command == "firmware":
        cmd_firmware_list()
    elif args.command == "download":
        cmd_download(args.version)
    elif args.command == "verify":
        cmd_verify()
    elif args.command == "upgrade":
        cmd_upgrade(args.version, simulate_failure=args.fail)
    elif args.command == "rollback":
        cmd_rollback()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
