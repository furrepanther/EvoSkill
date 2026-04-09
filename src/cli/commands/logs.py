"""evoskill logs — show run history."""

from pathlib import Path

import click
from pydantic import ValidationError
from rich.console import Console

from src.cli.config import load_config
from src.telemetry import RunTelemetry

console = Console()


def _parse_summary_from_telemetry(path: Path) -> tuple[str, str, str] | None:
    telemetry = RunTelemetry.load(path)
    if telemetry.baseline_score is None or telemetry.final_score is None:
        return None

    baseline = f"{telemetry.baseline_score:.1%}"
    final = f"{telemetry.final_score:.1%}"
    sign = "+" if telemetry.final_score >= telemetry.baseline_score else ""
    improvement = f"{sign}{(telemetry.final_score - telemetry.baseline_score):.1%}"
    return baseline, final, improvement


def _parse_summary(text: str) -> tuple[str, str, str]:
    """Extract baseline, final, improvement from a report markdown."""
    baseline = final = improvement = '?'
    for line in text.splitlines():
        if '| Baseline |' in line:
            baseline = line.split('|')[2].strip()
        elif '| Final |' in line:
            final = line.split('|')[2].strip()
        elif '| Improvement |' in line:
            improvement = line.split('|')[2].strip()
    return baseline, final, improvement


@click.command('logs')
@click.option('--last', default=5, show_default=True, help='Number of recent runs to show.')
def logs_cmd(last: int):
    """Show recent run history."""
    cfg = load_config()
    reports_dir = cfg.evoskill_dir / 'reports'

    if not reports_dir.exists():
        console.print('  No runs yet. Run [bold]evoskill run[/bold] first.')
        return

    reports = sorted(reports_dir.glob('run-*.md'), reverse=True)
    if not reports:
        console.print('  No reports found.')
        return

    telemetry_dir = cfg.evoskill_dir / 'telemetry'

    for report_path in reports[:last]:
        text = report_path.read_text()
        telemetry_path = telemetry_dir / f'{report_path.stem}.json'
        if telemetry_path.exists():
            try:
                parsed = _parse_summary_from_telemetry(telemetry_path)
            except (OSError, ValidationError, ValueError):
                parsed = None
            if parsed is not None:
                baseline, final, improvement = parsed
            else:
                baseline, final, improvement = _parse_summary(text)
        else:
            baseline, final, improvement = _parse_summary(text)
        console.print(f'  [bold]{report_path.stem}[/bold]  {baseline} → {final}  ({improvement})')
