"""evoskill schedule — run the loop on a fixed cadence."""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import time
from pathlib import Path

import click
from rich.console import Console

from src.watchdog_supervisor import (
    record_watchdog_supervisor_run_result,
    record_watchdog_supervisor_run_start,
    record_watchdog_supervisor_start,
    record_watchdog_supervisor_stop,
)

console = Console()
DEFAULT_INTERVAL_HOURS = 12.0
DEFAULT_MIN_FREE_MEMORY_MB = 2_048.0
DEFAULT_MAX_LOAD_PER_CPU = 1.5
DEFAULT_MIN_DISK_FREE_GB = 5.0
DEFAULT_STATUS_ENV = "ANTIGRAVITY_EVOSKILL_HEARTBEAT_FILE"


@dataclass(frozen=True)
class ResourceSnapshot:
    """Snapshot of local system resources."""

    load_1m: float | None
    cpu_count: int
    memory_available_mb: float | None
    memory_total_mb: float | None
    disk_free_gb: float | None
    disk_total_gb: float | None


def _find_project_root(start: Path | None = None) -> Path:
    current = Path.cwd() if start is None else start
    for parent in [current, *current.parents]:
        if (parent / ".evoskill").exists():
            return parent
    return current


def _read_meminfo() -> dict[str, int]:
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        return {}

    info: dict[str, int] = {}
    for line in meminfo_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            info[key] = int(parts[0])
        except ValueError:
            continue
    return info


def sample_resource_snapshot(project_root: Path | None = None) -> ResourceSnapshot:
    """Collect the current system resource state."""
    cpu_count = os.cpu_count() or 1
    load_1m: float | None
    try:
        load_1m = os.getloadavg()[0]
    except (AttributeError, OSError):
        load_1m = None

    meminfo = _read_meminfo()
    available_kb = meminfo.get("MemAvailable")
    total_kb = meminfo.get("MemTotal")
    if available_kb is None and total_kb is not None:
        available_kb = (
            meminfo.get("MemFree", 0)
            + meminfo.get("Buffers", 0)
            + meminfo.get("Cached", 0)
            + meminfo.get("SReclaimable", 0)
        )

    root = project_root or _find_project_root()
    try:
        disk_usage = shutil.disk_usage(root)
        disk_free_gb = disk_usage.free / (1024**3)
        disk_total_gb = disk_usage.total / (1024**3)
    except OSError:
        disk_free_gb = None
        disk_total_gb = None

    return ResourceSnapshot(
        load_1m=load_1m,
        cpu_count=cpu_count,
        memory_available_mb=(available_kb / 1024) if available_kb is not None else None,
        memory_total_mb=(total_kb / 1024) if total_kb is not None else None,
        disk_free_gb=disk_free_gb,
        disk_total_gb=disk_total_gb,
    )


def resource_pressure_reason(
    snapshot: ResourceSnapshot,
    *,
    min_free_memory_mb: float = DEFAULT_MIN_FREE_MEMORY_MB,
    max_load_per_cpu: float = DEFAULT_MAX_LOAD_PER_CPU,
    min_disk_free_gb: float = DEFAULT_MIN_DISK_FREE_GB,
) -> str | None:
    """Return a human-readable reason if the system is under pressure."""
    reasons: list[str] = []

    if snapshot.memory_available_mb is not None and snapshot.memory_available_mb < min_free_memory_mb:
        reasons.append(
            f"available memory {snapshot.memory_available_mb:.0f} MB < {min_free_memory_mb:.0f} MB"
        )

    if snapshot.load_1m is not None and snapshot.load_1m > snapshot.cpu_count * max_load_per_cpu:
        reasons.append(
            f"load avg {snapshot.load_1m:.2f} > {snapshot.cpu_count * max_load_per_cpu:.2f} threshold"
        )

    if snapshot.disk_free_gb is not None and snapshot.disk_free_gb < min_disk_free_gb:
        reasons.append(
            f"disk free {snapshot.disk_free_gb:.2f} GB < {min_disk_free_gb:.2f} GB"
        )

    if not reasons:
        return None
    return "; ".join(reasons)


def compute_next_run(started_at: datetime, interval_hours: float) -> datetime:
    """Return the next scheduled run time."""
    return started_at + timedelta(hours=interval_hours)


def seconds_until(moment: datetime, now: datetime | None = None) -> float:
    """Return the number of seconds until `moment`."""
    current = now or datetime.now(timezone.utc)
    return max(0.0, (moment - current).total_seconds())


def _format_optional_float(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}{suffix}"


def run_evoskill_once(*, continue_loop: bool, verbose: bool, quiet: bool):
    """Import and run the standard EvoSkill command once."""
    from src.cli.commands.run import run_cmd

    return run_cmd.callback(continue_loop=continue_loop, verbose=verbose, quiet=quiet)


def _format_local(moment: datetime) -> str:
    return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _scheduler_status_path(project_root: Path) -> Path:
    configured = os.getenv(DEFAULT_STATUS_ENV)
    if configured:
        return Path(configured)
    return project_root / ".evoskill" / "telemetry" / "scheduler_status.json"


def _write_scheduler_status(
    project_root: Path,
    *,
    status: str,
    mode: str,
    cycle: int,
    interval_hours: float,
    next_run: datetime | None = None,
    snapshot: ResourceSnapshot | None = None,
    last_run_status: str | None = None,
    pressure_reason: str | None = None,
    error: Exception | None = None,
    run_report=None,
) -> None:
    path = _scheduler_status_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": mode,
        "cycle": cycle,
        "interval_hours": interval_hours,
        "pid": os.getpid(),
        "project_root": str(project_root),
        "next_run_utc": next_run.isoformat() if next_run is not None else None,
        "resource_snapshot": asdict(snapshot) if snapshot is not None else None,
        "last_run_status": last_run_status,
        "pressure_reason": pressure_reason,
        "error": str(error) if error is not None else None,
        "run_id": getattr(run_report, "run_id", None),
        "report_path": (
            str(Path(run_report.project_root) / ".evoskill" / "reports" / f"run-{run_report.run_id}.md")
            if getattr(run_report, "run_id", None) and getattr(run_report, "project_root", None)
            else None
        ),
        "telemetry_path": (
            str(Path(run_report.project_root) / ".evoskill" / "telemetry" / f"run-{run_report.run_id}.json")
            if getattr(run_report, "run_id", None) and getattr(run_report, "project_root", None)
            else None
        ),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


@click.command("schedule")
@click.option(
    "--interval-hours",
    default=DEFAULT_INTERVAL_HOURS,
    show_default=True,
    type=click.FloatRange(min=0.1),
    help="Hours between scheduled runs. The default is twice daily.",
)
@click.option(
    "--min-free-memory-mb",
    default=DEFAULT_MIN_FREE_MEMORY_MB,
    show_default=True,
    type=click.FloatRange(min=0.0),
    help="Skip a cycle when available memory falls below this threshold.",
)
@click.option(
    "--max-load-per-cpu",
    default=DEFAULT_MAX_LOAD_PER_CPU,
    show_default=True,
    type=click.FloatRange(min=0.0),
    help="Skip a cycle when 1-minute load average exceeds cpu_count * this value.",
)
@click.option(
    "--min-disk-free-gb",
    default=DEFAULT_MIN_DISK_FREE_GB,
    show_default=True,
    type=click.FloatRange(min=0.0),
    help="Skip a cycle when free disk space falls below this threshold.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Show per-sample results during each run.",
)
@click.option(
    "--quiet",
    is_flag=True,
    default=False,
    help="Show only the progress table during each run.",
)
def schedule_cmd(
    interval_hours: float,
    min_free_memory_mb: float,
    max_load_per_cpu: float,
    min_disk_free_gb: float,
    verbose: bool,
    quiet: bool,
) -> None:
    """Run `evoskill run --continue` on a fixed cadence."""
    project_root = _find_project_root()
    console.print(
        f"\n  [bold]EvoSkill[/bold] — scheduled mode  |  every {interval_hours:g} hours\n"
    )
    console.print("  Press Ctrl-C to stop.\n")

    cycle = 0
    scheduler_started_at = datetime.now(timezone.utc)
    _write_scheduler_status(
        project_root,
        status="up",
        mode="starting",
        cycle=cycle,
        interval_hours=interval_hours,
    )
    start_write = record_watchdog_supervisor_start(
        interval_hours=interval_hours,
        min_free_memory_mb=min_free_memory_mb,
        max_load_per_cpu=max_load_per_cpu,
        min_disk_free_gb=min_disk_free_gb,
        observed_at_utc=scheduler_started_at.isoformat(),
    )
    if start_write.status in {"error", "unavailable"}:
        console.print(
            f"  [yellow]Memory Fabric write failed[/yellow] (watchdog start): {start_write.detail or start_write.status}"
        )

    stop_reason = "keyboard_interrupt"
    try:
        while True:
            cycle += 1
            started_at = datetime.now(timezone.utc)
            next_run = compute_next_run(started_at, interval_hours)

            snapshot = sample_resource_snapshot()
            _write_scheduler_status(
                project_root,
                status="up",
                mode="running",
                cycle=cycle,
                interval_hours=interval_hours,
                next_run=next_run,
                snapshot=snapshot,
            )
            run_start_write = record_watchdog_supervisor_run_start(
                cycle=cycle,
                started_at_utc=started_at.isoformat(),
                next_run_utc=next_run.isoformat(),
                resource_snapshot=snapshot,
                observed_at_utc=started_at.isoformat(),
            )
            if run_start_write.status in {"error", "unavailable"}:
                console.print(
                    f"  [yellow]Memory Fabric write failed[/yellow] (watchdog run start): {run_start_write.detail or run_start_write.status}"
                )

            pressure_reason = resource_pressure_reason(
                snapshot,
                min_free_memory_mb=min_free_memory_mb,
                max_load_per_cpu=max_load_per_cpu,
                min_disk_free_gb=min_disk_free_gb,
            )
            if pressure_reason:
                result_write = record_watchdog_supervisor_run_result(
                    cycle=cycle,
                    status="skipped_due_to_pressure",
                    started_at_utc=started_at.isoformat(),
                    completed_at_utc=datetime.now(timezone.utc).isoformat(),
                    next_run_utc=next_run.isoformat(),
                    resource_snapshot=snapshot,
                    pressure_reason=pressure_reason,
                    observed_at_utc=datetime.now(timezone.utc).isoformat(),
                )
                if result_write.status in {"error", "unavailable"}:
                    console.print(
                        f"  [yellow]Memory Fabric write failed[/yellow] (watchdog run result): {result_write.detail or result_write.status}"
                    )
                _write_scheduler_status(
                    project_root,
                    status="up",
                    mode="sleeping",
                    cycle=cycle,
                    interval_hours=interval_hours,
                    next_run=next_run,
                    snapshot=snapshot,
                    last_run_status="skipped_due_to_pressure",
                    pressure_reason=pressure_reason,
                )
                console.print(
                    f"  [yellow]Skipping cycle {cycle} due to system pressure:[/yellow] {pressure_reason}"
                )
                console.print(
                    f"  Next cycle at {_format_local(next_run)} ({seconds_until(next_run) / 3600:.2f} hours from now)\n"
                )
                time.sleep(seconds_until(next_run))
                continue

            console.print(
                f"  [bold]Cycle {cycle}[/bold] starting at {_format_local(started_at)}"
            )
            console.print(
                "  Resources: "
                f"load={_format_optional_float(snapshot.load_1m)}, "
                f"free_mem={_format_optional_float(snapshot.memory_available_mb)} MB, "
                f"disk_free={_format_optional_float(snapshot.disk_free_gb)} GB"
            )
            run_report = None
            run_error: Exception | None = None
            try:
                run_report = run_evoskill_once(continue_loop=True, verbose=verbose, quiet=quiet)
            except Exception as exc:  # pragma: no cover - exercised through integration
                run_error = exc
                console.print(
                    f"  [red]Scheduled run failed:[/red] {exc}"
                )
            result_write = record_watchdog_supervisor_run_result(
                cycle=cycle,
                status="failed" if run_error is not None else "success",
                started_at_utc=started_at.isoformat(),
                completed_at_utc=datetime.now(timezone.utc).isoformat(),
                next_run_utc=next_run.isoformat(),
                resource_snapshot=snapshot,
                report=run_report,
                error=run_error,
                observed_at_utc=datetime.now(timezone.utc).isoformat(),
            )
            if result_write.status in {"error", "unavailable"}:
                console.print(
                    f"  [yellow]Memory Fabric write failed[/yellow] (watchdog run result): {result_write.detail or result_write.status}"
                )
            _write_scheduler_status(
                project_root,
                status="degraded" if run_error is not None else "up",
                mode="sleeping",
                cycle=cycle,
                interval_hours=interval_hours,
                next_run=next_run,
                snapshot=snapshot,
                last_run_status="failed" if run_error is not None else "success",
                error=run_error,
                run_report=run_report,
            )

            sleep_seconds = seconds_until(next_run)
            console.print(
                f"  Next run at {_format_local(next_run)} "
                f"({sleep_seconds / 3600:.2f} hours from now)\n"
            )
            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        console.print("\n  [yellow]Scheduled mode stopped.[/yellow]")
        stop_reason = "keyboard_interrupt"
    except Exception as exc:
        stop_reason = f"unexpected_error: {exc}"
        console.print(f"\n  [red]Scheduled mode failed:[/red] {exc}")
        raise
    finally:
        stop_write = record_watchdog_supervisor_stop(
            cycle=cycle,
            reason=stop_reason,
            observed_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        _write_scheduler_status(
            project_root,
            status="down",
            mode="stopped",
            cycle=cycle,
            interval_hours=interval_hours,
        )
        if stop_write.status in {"error", "unavailable"}:
            console.print(
                f"  [yellow]Memory Fabric write failed[/yellow] (watchdog stop): {stop_write.detail or stop_write.status}"
            )
