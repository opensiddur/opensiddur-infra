import json
import mimetypes
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

import yaml

from .builds import Builds, Rejected
from .config import Config
from .progress import Progress, build_steps, copy_log
from .storage import Storage
from .store import FirestoreStore


class Stopped(Exception):
    pass


def execute(identifier, config=None, store=None, storage=None):
    config = config or Config()
    store = store or FirestoreStore(config.project)
    storage = storage or Storage(config)
    builds = Builds(store, config.release)
    execution = os.getenv("CLOUD_RUN_EXECUTION", "preview-" + identifier)
    row = builds.claim(identifier, execution)
    if row is None:
        return
    results, artifacts = {}, []
    started = time.monotonic()

    def alive(ignore_time=False):
        current = store.get(f"build:{identifier}")
        account = store.get(f"account:{row['owner']}")
        if (
            not current
            or current.get("cancel")
            or current.get("deleted")
            or not account
            or not account.get("enabled")
            or not account.get("consent")
        ):
            raise Stopped("Cancelled")
        if not ignore_time and time.monotonic() - started >= row["seconds"] - min(
            30, row["seconds"] * 0.2
        ):
            raise Stopped("Runtime allowance reached")
        builds.update(identifier)

    with tempfile.TemporaryDirectory(prefix="siddur-") as temporary:
        work = Path(temporary)
        out = work / "artifacts"
        out.mkdir()
        progress = Progress(
            builds,
            identifier,
            row.get("steps") or build_steps(row["type"], row["formats"]),
        )
        progress.set("prepare", "running")
        checkpoint_artifacts = []
        last_checkpoint = time.monotonic()
        progress_file = work / "progress.json"

        def collect_logs():
            names = []
            if copy_log(work / "worker.log", out / "worker.log"):
                names.append("worker.log")
            for source in sorted((work / "pdf-build").glob("*")):
                if source.suffix in {".log", ".blg"}:
                    name = "pdf" + source.suffix
                    if copy_log(source, out / name):
                        names.append(name)
            return names

        def checkpoint_logs():
            nonlocal checkpoint_artifacts, last_checkpoint
            alive(ignore_time=True)
            last_checkpoint = time.monotonic()
            try:
                checkpoint_artifacts = [
                    storage.put(
                        f"builds/{identifier}/{name}",
                        (out / name).read_bytes(),
                        "text/plain",
                    )
                    for name in collect_logs()
                ]
            except Exception:
                return  # A temporary log-upload problem must not stop the compiler.
            alive(ignore_time=True)
            builds.update(identifier, artifacts=checkpoint_artifacts)

        try:
            db = work / "reference.db"
            shutil.copyfile(Path(config.processor) / "database/reference.db", db)
            settings = json.loads(json.dumps(row["settings"]))
            (out / "settings.yaml").write_text(
                yaml.safe_dump(settings, allow_unicode=True, sort_keys=False)
            )
            if row.get("asset"):
                asset = store.get("asset:" + row["asset"])
                if asset and asset["owner"] == row["owner"]:
                    logo = out / "logo.png"
                    logo.write_bytes(storage.read(asset["object"]))
                    distribution = settings.setdefault("distribution", {})
                    if distribution.get("notice") == "none":
                        raise ValueError("Enable the distribution notice to use a logo")
                    distribution.setdefault("notice", {})["logo"] = str(logo)
                    portable = row["settings"].copy()
                    portable = json.loads(json.dumps(portable))
                    portable.setdefault("distribution", {}).setdefault("notice", {})[
                        "logo"
                    ] = "logo.png"
                    (out / "settings.yaml").write_text(
                        yaml.safe_dump(portable, allow_unicode=True, sort_keys=False)
                    )
            if row["type"] != "full":
                settings["book"] = {"project": "infra_demo", "file_name": "index.xml"}
                # The demonstration explicitly includes a fallback source; full builds do not.
                priorities = settings.setdefault("priority", {}).setdefault(
                    "transclusion", []
                )
                for source in (row["settings"]["book"]["project"], "tanakh-wlc-he"):
                    if source not in priorities:
                        priorities.append(source)
                settings.setdefault("declarations", {}).setdefault(
                    "opensiddur:paratext", {}
                ).update({"title-page": False, "include": False})
            settings_file = work / "settings.yaml"
            settings_file.write_text(
                yaml.safe_dump(settings, allow_unicode=True, sort_keys=False)
            )
            env = os.environ | {
                "REFERENCE_DB": str(db),
                "BUILD_PROGRESS_FILE": str(progress_file),
                "openin_any": "p",
                "openout_any": "p",
                "shell_escape": "0",
                "TEXMFOUTPUT": str(work),
                "TMPDIR": str(work),
            }

            progress.set("prepare", "succeeded")

            def run(module, args, stage):
                alive()
                step = (
                    "compile-" + str(args[args.index("--destination") + 1])
                    if module.endswith("compiler")
                    else {
                        "opensiddur.exporter.html.html": "html",
                        "opensiddur.exporter.tex.latex": "tex",
                        "opensiddur.exporter.pdf.pdf": "pdf",
                    }[module]
                )
                progress.set(step, "running")
                # Logs stay in the temporary build directory; never emit rendered text to Cloud Logging.
                with (work / "worker.log").open("ab") as log:
                    log.write(("\n=== " + stage + " ===\n").encode())
                    log.flush()
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "opensiddur_infra.runner",
                            module,
                            *map(str, args),
                        ],
                        cwd=work,
                        env=env,
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )
                    try:
                        while process.poll() is None:
                            time.sleep(1)
                            alive()
                            if step == "pdf" and progress_file.exists():
                                try:
                                    progress.pdf_pass(
                                        json.loads(progress_file.read_text())
                                    )
                                except (OSError, ValueError):
                                    pass
                            if time.monotonic() - last_checkpoint >= 20:
                                checkpoint_logs()
                            if (
                                sum(
                                    p.stat().st_size
                                    for p in out.iterdir()
                                    if p.is_file()
                                )
                                > 250 * 1024**2
                            ):
                                raise Stopped("Output exceeds 250 MiB")
                        if step == "pdf" and progress_file.exists():
                            try:
                                progress.pdf_pass(json.loads(progress_file.read_text()))
                            except (OSError, ValueError):
                                pass
                        if process.returncode:
                            if (
                                os.getenv("SAMPLE_DIAGNOSTICS") == "true"
                                and row["settings"].get("book", {}).get("project")
                                == "infra_demo"
                            ):
                                print(
                                    (work / "worker.log").read_text(errors="replace")[
                                        -6000:
                                    ],
                                    file=sys.stderr,
                                )
                            raise RuntimeError(
                                f"{stage} failed. Download the build logs for details."
                            )
                        progress.set(step, "succeeded")
                    except Exception:
                        progress.set(step, "failed")
                        raise
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()

            def compile_file(destination):
                compiled = work / f"compiled-{destination}.xml"
                if not compiled.exists():
                    run(
                        "opensiddur.exporter.compiler",
                        [
                            "-s",
                            settings_file,
                            "--destination",
                            destination,
                            "-o",
                            compiled,
                        ],
                        f"Compiling {destination} text",
                    )
                return compiled

            formats = (
                ["html"]
                if row["type"] == "html"
                else ["pdf"]
                if row["type"] == "pdf"
                else row["formats"]
            )
            for output in sorted(
                formats,
                key=lambda value: {"html": 0, "xml": 1, "tex": 2, "pdf": 3}[value],
            ):
                try:
                    if output == "html":
                        destination = "print" if row["type"] == "html" else "electronic"
                        compiled = compile_file(destination)
                        filename = (
                            "preview.html" if row["type"] == "html" else "book.html"
                        )
                        run(
                            "opensiddur.exporter.html.html",
                            [compiled, out / filename, "-s", settings_file],
                            "Rendering HTML",
                        )
                    else:
                        compiled = compile_file("print")
                        if output == "xml":
                            progress.set("xml", "running")
                            shutil.copyfile(compiled, out / "compiled-print.xml")
                            if "html" in formats:
                                shutil.copyfile(
                                    compile_file("electronic"),
                                    out / "compiled-electronic.xml",
                                )
                            progress.set("xml", "succeeded")
                        elif output == "tex":
                            run(
                                "opensiddur.exporter.tex.latex",
                                [compiled, "-s", settings_file, "-o", out / "book.tex"],
                                "Rendering TeX",
                            )
                        else:
                            run(
                                "opensiddur.exporter.pdf.pdf",
                                [
                                    compiled,
                                    out / "book.pdf",
                                    "-s",
                                    settings_file,
                                    "--build-dir",
                                    work / "pdf-build",
                                    "--tex-output",
                                    work / "pdf-source.tex",
                                ],
                                "Typesetting PDF",
                            )
                    results[output] = {"state": "succeeded"}
                except (RuntimeError, Stopped) as exc:
                    if isinstance(exc, Stopped) and str(exc) == "Cancelled":
                        raise
                    results[output] = {"state": "failed", "message": str(exc)}
                    if isinstance(exc, Stopped):
                        break
            if (out / "book.tex").exists() and (out / "logo.png").exists():
                tex = out / "book.tex"
                tex.write_text(
                    tex.read_text().replace(str(out / "logo.png"), "logo.png")
                )
            for requested in formats:
                results.setdefault(
                    requested,
                    {"state": "skipped", "message": "Runtime allowance reached"},
                )
            progress.set("package", "running")
            collect_logs()
            manifest = json.loads((Path(config.bundle) / "release.json").read_text())
            manifest.update(
                build_id=identifier,
                formats=results,
                sample=row["type"] != "full",
                image=os.getenv("IMAGE_DIGEST", "development"),
            )
            if row["type"] != "full":
                manifest["sample_notice"] = (
                    "Fixed Psalm 23 demonstration; WLC fallback and front-matter overrides apply only to this sample. Selected sources may have no coverage."
                )
            (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
            if row["type"] == "full":
                shutil.copyfile(
                    Path(config.bundle) / "notices.json", out / "software-notices.json"
                )
            with zipfile.ZipFile(
                out / "artifacts.zip", "w", zipfile.ZIP_DEFLATED
            ) as archive:
                for path in out.iterdir():
                    if path.name != "artifacts.zip":
                        archive.write(path, path.name)
            if sum(p.stat().st_size for p in out.iterdir()) > 250 * 1024**2:
                raise Stopped("Output exceeds 250 MiB")
            progress.set("package", "succeeded")
            progress.set("upload", "running")
            for path in out.iterdir():
                alive(ignore_time=True)
                artifacts.append(
                    storage.put(
                        f"builds/{identifier}/{path.name}",
                        path.read_bytes(),
                        mimetypes.guess_type(path.name)[0]
                        or "application/octet-stream",
                    )
                )
            alive(ignore_time=True)
            progress.set("upload", "succeeded")
            success = sum(r["state"] == "succeeded" for r in results.values())
            builds.finish(
                identifier,
                "succeeded"
                if success == len(formats)
                else "partial"
                if success
                else "failed",
                results,
                artifacts,
            )
            if store.get(f"build:{identifier}").get("cancel"):
                storage.delete_prefix(f"builds/{identifier}/")
        except Exception as exc:
            # Keep private diagnostics on failures, but never publish after cancellation,
            # deletion or withdrawal. Other incomplete uploads remain unreferenced.
            with (work / "worker.log").open("a") as log:
                traceback.print_exc(file=log)
            try:
                checkpoint_logs()
                alive(ignore_time=True)
            except Stopped:
                checkpoint_artifacts = []
                storage.delete_prefix(f"builds/{identifier}/")
            builds.finish(
                identifier,
                "failed",
                {
                    "build": {
                        "state": "failed",
                        "message": str(exc)
                        if isinstance(exc, Stopped)
                        else "Build failed. Download the build logs for details.",
                    }
                },
                checkpoint_artifacts,
            )
            raise RuntimeError(
                "Build failed; private diagnostics recorded when available"
            ) from None


def preview_app():
    from fastapi import FastAPI, HTTPException

    app = FastAPI()

    @app.post("/process")
    def process(data: dict):
        try:
            execute(data["id"])
        except Rejected as exc:
            raise HTTPException(exc.status, str(exc)) from None
        except Exception:
            # Terminal failure has been recorded. Acknowledging avoids expensive retries.
            return {"ok": False}
        return {"ok": True}

    return app


if __name__ == "__main__":
    execute(os.environ["BUILD_ID"])
