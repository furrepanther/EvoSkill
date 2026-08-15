"""Minimal scheduler entrypoint for long-running EvoSkill supervision."""

from src.cli.commands.schedule import schedule_cmd


if __name__ == "__main__":
    schedule_cmd()
