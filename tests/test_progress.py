import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from opensiddur_infra.builds import Builds
from opensiddur_infra.config import Config
from opensiddur_infra.progress import build_steps, copy_log
from opensiddur_infra.store import MemoryStore
from opensiddur_infra.worker import execute


class Outputs:
    def __init__(self):
        self.files = {}

    def put(self, name, data, content_type):
        self.files[name] = data
        return {
            "name": name.rsplit("/", 1)[-1],
            "object": name,
            "size": len(data),
            "content_type": content_type,
        }

    def delete_prefix(self, prefix):
        self.files = {
            key: value
            for key, value in self.files.items()
            if not key.startswith(prefix)
        }


class ProgressTests(unittest.TestCase):
    def test_plan_deduplicates_compilation_and_preserves_execution_order(self):
        self.assertEqual(
            [step["id"] for step in build_steps("full", ["pdf", "html", "xml", "tex"])],
            [
                "prepare",
                "compile-electronic",
                "html",
                "compile-print",
                "xml",
                "tex",
                "pdf",
                "package",
                "upload",
            ],
        )
        self.assertEqual(
            [step["id"] for step in build_steps("html", ["html"])],
            ["prepare", "compile-print", "html", "package", "upload"],
        )

    def test_logs_are_bounded_and_keep_the_beginning_and_error_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source", Path(directory) / "target"
            source.write_bytes(b"BEGIN" + b"x" * 5000 + b"ERROR END")
            self.assertTrue(copy_log(source, target, limit=1024))
            data = target.read_bytes()
            self.assertLessEqual(len(data), 1024)
            self.assertTrue(data.startswith(b"BEGIN"))
            self.assertTrue(data.endswith(b"ERROR END"))
            self.assertIn(b"Log truncated", data)

    def run_worker(self, cancel=False):
        store, outputs = MemoryStore(), Outputs()
        store.atomic(
            ["account:owner"],
            lambda rows: rows.update(
                {
                    "account:owner": {
                        "kind": "account",
                        "owner": "owner",
                        "enabled": True,
                        "consent": {"version": "test"},
                    }
                }
            ),
        )
        builds = Builds(store, "test")
        row = builds.submit(
            "owner", {"book": {"project": "synthetic"}}, ["pdf"], "full", "test"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "database").mkdir()
            (root / "database/reference.db").write_bytes(b"synthetic DB")
            (root / "release.json").write_text(json.dumps({"release": "test"}))
            (root / "notices.json").write_text("{}")
            config = replace(
                Config(), release="test", processor=str(root), bundle=str(root)
            )

            class Process:
                pid = 123

                def __init__(self, command, **kwargs):
                    module = command[3]
                    self.returncode = 1 if module.endswith("pdf.pdf") else 0
                    self.first = True
                    if self.returncode:
                        kwargs["stdout"].write(b"SYNTHETIC PDF ERROR\n")
                        kwargs["stdout"].flush()
                        build_dir = Path(command[command.index("--build-dir") + 1])
                        build_dir.mkdir()
                        (build_dir / "output.log").write_text("Synthetic TeX failure")
                        Path(kwargs["env"]["BUILD_PROGRESS_FILE"]).write_text(
                            json.dumps({"pass": 2, "phase": "typesetting"})
                        )
                        if cancel:
                            builds.cancel("owner", row["id"])
                    else:
                        Path(command[command.index("-o") + 1]).write_text(
                            "<synthetic/>"
                        )

                def poll(self):
                    if self.first:
                        self.first = False
                        return None
                    return self.returncode

                def wait(self):
                    return self.returncode

            with (
                patch("opensiddur_infra.worker.subprocess.Popen", Process),
                patch("opensiddur_infra.worker.time.sleep"),
            ):
                if cancel:
                    with self.assertRaises(RuntimeError):
                        execute(row["id"], config, store, outputs)
                else:
                    execute(row["id"], config, store, outputs)
        return builds.get("owner", row["id"]), outputs

    def test_pdf_failure_preserves_private_logs_and_actual_pass(self):
        row, outputs = self.run_worker()
        self.assertEqual(row["state"], "failed")
        steps = {step["id"]: step for step in row["steps"]}
        self.assertEqual(steps["compile-print"]["state"], "succeeded")
        self.assertEqual(steps["pdf"]["state"], "failed")
        self.assertEqual(steps["pdf"]["pass_number"], 2)
        self.assertEqual(steps["upload"]["state"], "succeeded")
        logs = {
            item["name"]: outputs.files[item["object"]]
            for item in row["artifacts"]
            if item["name"].endswith(".log")
        }
        self.assertIn(b"SYNTHETIC PDF ERROR", logs["worker.log"])
        self.assertEqual(logs["pdf.log"], b"Synthetic TeX failure")
        self.assertNotIn("SYNTHETIC", json.dumps(row["results"]))

    def test_cancellation_does_not_publish_logs_or_artifacts(self):
        row, outputs = self.run_worker(cancel=True)
        self.assertEqual(row["state"], "cancelled")
        self.assertEqual(row["artifacts"], [])
        self.assertEqual(outputs.files, {})

    def test_crash_finalization_keeps_only_checkpointed_private_logs(self):
        store = MemoryStore()
        store.atomic(
            ["account:owner"],
            lambda rows: rows.update(
                {"account:owner": {"enabled": True, "consent": {"version": "test"}}}
            ),
        )
        builds = Builds(store, "test")
        row = builds.submit("owner", {}, ["pdf"], "full", "crash")
        builds.claim(row["id"], "synthetic")
        artifacts = [
            {"name": "worker.log", "object": "private/worker.log"},
            {"name": "book.pdf", "object": "private/book.pdf"},
        ]
        builds.update(row["id"], artifacts=artifacts)
        builds.finish(row["id"], "failed")
        self.assertEqual(builds.get("owner", row["id"])["artifacts"], artifacts[:1])


class RunnerTests(unittest.TestCase):
    def test_logo_is_copied_and_only_its_generated_path_becomes_relative(self):
        from opensiddur_infra.runner import portable_notice_renderer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            source.write_bytes(b"synthetic-logo")
            output = root / "render" / "book.tex"

            def original(notice, logo):
                return (
                    "notice " + notice + " \\includegraphics{" + logo.as_posix() + "}"
                )

            renderer = portable_notice_renderer(original, output)
            self.assertEqual(
                renderer("credit", source), "notice credit \\includegraphics{logo.png}"
            )
            self.assertEqual(
                (output.parent / "logo.png").read_bytes(), b"synthetic-logo"
            )
            self.assertEqual(
                renderer("credit", output.parent / "logo.png"),
                "notice credit \\includegraphics{logo.png}",
            )

    def test_pdf_pass_reporting_tracks_actual_subprocess_launches(self):
        import sys
        import types
        from opensiddur_infra import runner

        fake = types.ModuleType("opensiddur.exporter.refdb")

        class ReferenceDatabase:
            def __init__(self, path=None):
                pass

        fake.ReferenceDatabase = ReferenceDatabase
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "progress.json"

            def program(*args, **kwargs):
                import subprocess

                subprocess.run(["lualatex", "synthetic.tex"])
                self.assertEqual(
                    json.loads(event.read_text()), {"pass": 1, "phase": "typesetting"}
                )
                subprocess.run(["bibtex", "synthetic"])
                self.assertEqual(
                    json.loads(event.read_text()), {"pass": 1, "phase": "bibliography"}
                )
                subprocess.run(["lualatex", "synthetic.tex"])

            with (
                patch.dict(sys.modules, {"opensiddur.exporter.refdb": fake}),
                patch.dict(
                    "os.environ",
                    {"REFERENCE_DB": "synthetic.db", "BUILD_PROGRESS_FILE": str(event)},
                ),
                patch.object(sys, "argv", ["runner", "synthetic.module"]),
                patch("subprocess.run") as invoke,
                patch("runpy.run_module", side_effect=program),
            ):
                runner.main()
                self.assertEqual(invoke.call_count, 3)
            self.assertEqual(
                json.loads(event.read_text()), {"pass": 2, "phase": "typesetting"}
            )
