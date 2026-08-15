from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gemini_cli import (  # noqa: E402
    GEMINI_DEFAULT_MODEL,
    GEMINI_MODEL_PREFERENCE,
    GeminiCLIResult,
    GeminiModelSelection,
    GeminiQuotaBucket,
    GeminiQuotaProbe,
    build_gemini_model_chain,
    build_gemini_prompt,
    probe_gemini_quota,
    infer_llm_provider,
    normalize_gemini_model,
    resolve_gemini_command,
    select_gemini_model_from_probe,
    run_gemini_cli,
)


class FakeProcess:
    def __init__(self, *, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.stdin_payload: bytes | None = None

    async def communicate(self, input: bytes | None = None):
        self.stdin_payload = input
        return self._stdout, self._stderr


class GeminiCliTests(unittest.IsolatedAsyncioTestCase):
    def test_resolve_gemini_command_prefers_override(self) -> None:
        with patch.dict(os.environ, {"EVOSKILL_GEMINI_CLI": "/custom/gemini"}):
            self.assertEqual(resolve_gemini_command(), ["/custom/gemini"])

    def test_resolve_gemini_command_prefers_repo_binary(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            binary = repo_root / "node_modules" / ".bin" / "gemini"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n")

            with patch.dict(os.environ, {}, clear=True), patch(
                "src.gemini_cli.GEMINI_CLI_REPO",
                repo_root,
            ), patch("src.gemini_cli.shutil.which", return_value=None):
                self.assertEqual(resolve_gemini_command(), [str(binary)])

    def test_resolve_gemini_command_prefers_bundle_when_binary_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            bundle = repo_root / "bundle" / "gemini.js"
            bundle.parent.mkdir(parents=True)
            bundle.write_text("console.log('bundle');\n")

            with patch.dict(os.environ, {}, clear=True), patch(
                "src.gemini_cli.GEMINI_CLI_REPO",
                repo_root,
            ), patch("src.gemini_cli.shutil.which", return_value=None):
                self.assertEqual(resolve_gemini_command(), ["node", str(bundle)])

    def test_resolve_gemini_command_raises_when_local_binary_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            with patch.dict(os.environ, {}, clear=True), patch(
                "src.gemini_cli.GEMINI_CLI_REPO",
                repo_root,
            ), patch("src.gemini_cli.shutil.which", return_value=None):
                with self.assertRaises(RuntimeError):
                    resolve_gemini_command()

    def test_normalize_gemini_model_preserves_gemini_prefix(self) -> None:
        self.assertEqual(normalize_gemini_model("gemini-3.1-pro-preview"), "gemini-3.1-pro-preview")
        self.assertEqual(normalize_gemini_model(""), GEMINI_DEFAULT_MODEL)
        self.assertEqual(normalize_gemini_model(None), GEMINI_DEFAULT_MODEL)
        self.assertEqual(normalize_gemini_model("sonnet"), GEMINI_DEFAULT_MODEL)

    def test_build_gemini_prompt_keeps_system_prompt_first(self) -> None:
        prompt = build_gemini_prompt("system rules", "user question")
        self.assertEqual(prompt, "system rules\n\nuser question")

    def test_build_gemini_model_chain_prefers_fixed_chain(self) -> None:
        self.assertEqual(build_gemini_model_chain(), GEMINI_MODEL_PREFERENCE)
        self.assertEqual(
            build_gemini_model_chain("gemini-2.5-flash"),
            ("gemini-2.5-flash", *GEMINI_MODEL_PREFERENCE),
        )

    def test_select_gemini_model_prefers_first_available_model(self) -> None:
        probe = GeminiQuotaProbe(
            fetched=True,
            buckets={
                "gemini-3.1-pro-preview": GeminiQuotaBucket(
                    model="gemini-3.1-pro-preview",
                    remaining_amount=0,
                    remaining_fraction=0.0,
                    reset_time="2026-04-09T00:00:00Z",
                ),
                "gemini-3-flash-preview": GeminiQuotaBucket(
                    model="gemini-3-flash-preview",
                    remaining_amount=None,
                    remaining_fraction=0.5,
                    reset_time="2026-04-09T01:00:00Z",
                ),
                "gemini-2.5-pro": GeminiQuotaBucket(
                    model="gemini-2.5-pro",
                    remaining_amount=10,
                    remaining_fraction=0.1,
                    reset_time="2026-04-09T02:00:00Z",
                ),
            },
            raw={"fetched": True},
            duration_ms=12,
            command=("node",),
        )

        selection = select_gemini_model_from_probe(GEMINI_MODEL_PREFERENCE, probe)
        self.assertIsInstance(selection, GeminiModelSelection)
        self.assertEqual(selection.selected_model, "gemini-3-flash-preview")
        self.assertEqual(selection.reason, "quota available")

    def test_select_gemini_model_raises_when_all_exhausted(self) -> None:
        probe = GeminiQuotaProbe(
            fetched=True,
            buckets={
                "gemini-3.1-pro-preview": GeminiQuotaBucket(
                    model="gemini-3.1-pro-preview",
                    remaining_amount=0,
                    remaining_fraction=0.0,
                    reset_time=None,
                ),
                "gemini-3-flash-preview": GeminiQuotaBucket(
                    model="gemini-3-flash-preview",
                    remaining_amount=0,
                    remaining_fraction=0.0,
                    reset_time=None,
                ),
                "gemini-2.5-pro": GeminiQuotaBucket(
                    model="gemini-2.5-pro",
                    remaining_amount=0,
                    remaining_fraction=0.0,
                    reset_time=None,
                ),
            },
            raw={"fetched": True},
            duration_ms=12,
            command=("node",),
        )

        with self.assertRaises(RuntimeError):
            select_gemini_model_from_probe(GEMINI_MODEL_PREFERENCE, probe)

    def test_infer_provider_defaults_to_google_for_non_openai_models(self) -> None:
        self.assertEqual(infer_llm_provider("gemini-3.1-pro-preview"), "google")
        self.assertEqual(infer_llm_provider("mistral-small"), "google")
        self.assertEqual(infer_llm_provider("gpt-4o"), "openai")

    async def test_probe_gemini_quota_parses_json_snapshot(self) -> None:
        fake_process = FakeProcess(
            stdout=b'{"fetched":true,"buckets":[{"modelId":"gemini-3.1-pro-preview","remainingFraction":0.75,"resetTime":"2026-04-09T00:00:00Z"}]}',
        )

        async def fake_create_subprocess_exec(*args, **kwargs):
            self.assertEqual(args[0], "node")
            self.assertIn("--input-type=module", args)
            self.assertIn("-e", args)
            self.assertEqual(kwargs["cwd"], str(Path("/tmp/work").resolve()))
            self.assertEqual(
                kwargs["env"]["GOOGLE_GENAI_USE_GCA"],
                "true",
            )
            return fake_process

        with patch("src.gemini_cli._resolve_gemini_bundle_core_path", return_value=Path("/tmp/core.js")), patch(
            "src.gemini_cli.asyncio.create_subprocess_exec",
            side_effect=fake_create_subprocess_exec,
        ):
            probe = await probe_gemini_quota(
                GEMINI_MODEL_PREFERENCE,
                cwd=Path("/tmp/work"),
            )

        self.assertTrue(probe.fetched)
        self.assertIn("gemini-3.1-pro-preview", probe.buckets)
        self.assertEqual(probe.buckets["gemini-3.1-pro-preview"].remaining_fraction, 0.75)
        self.assertEqual(fake_process.returncode, 0)

    async def test_run_gemini_cli_parses_json_wrapper(self) -> None:
        fake_process = FakeProcess(stdout=b'{"response":"ok","stats":{"tokens":12}}')

        async def fake_create_subprocess_exec(*args, **kwargs):
            self.assertEqual(args[0], "gemini")
            self.assertIn("--model", args)
            self.assertIn("--approval-mode", args)
            self.assertEqual(kwargs["cwd"], str(Path("/tmp/work").resolve()))
            self.assertEqual(kwargs["env"]["GOOGLE_GENAI_USE_GCA"], "true")
            return fake_process

        with patch("src.gemini_cli.resolve_gemini_command", return_value=["gemini"]), patch(
            "src.gemini_cli.asyncio.create_subprocess_exec",
            side_effect=fake_create_subprocess_exec,
        ):
            result = await run_gemini_cli(
                "hello world",
                model="sonnet",
                cwd=Path("/tmp/work"),
                include_directories=["/tmp/include"],
                extra_args=["--foo", "bar"],
            )

        self.assertIsInstance(result, GeminiCLIResult)
        self.assertEqual(result.response, "ok")
        self.assertEqual(result.stats["tokens"], 12)
        self.assertEqual(fake_process.stdin_payload, b"hello world")
        self.assertEqual(result.command[0], "gemini")


if __name__ == "__main__":
    unittest.main()
