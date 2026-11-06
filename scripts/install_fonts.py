"""Install the pinned Open Siddur font pack and retain its licensing documents."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def install(source, destination, documentation, lock):
    installed = []
    for path in sorted((source / "Fonts").rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source / "Fonts")
        if path.suffix.lower() in {".ttf", ".otf", ".ttc"}:
            target = destination / relative
            installed.append(str(relative))
        elif path.suffix.lower() in {".txt", ".md", ".html"} or any(
            marker in path.name.lower()
            for marker in ("license", "copying", "copyright", "ofl", "readme")
        ):
            target = documentation / "Fonts" / relative
        else:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        target.chmod(0o644)
    documentation.mkdir(parents=True, exist_ok=True)
    for name in ("README.txt", "LICENSES.txt", "CHANGES.txt", "INSTALL.txt"):
        shutil.copyfile(source / name, documentation / name)
    (documentation / "manifest.json").write_text(
        json.dumps({**lock, "installed": installed}, indent=2)
    )
    if not installed:
        raise RuntimeError("The pinned font pack contains no installable fonts")


if __name__ == "__main__":
    lock = json.loads(Path("fonts.lock.json").read_text())
    with tempfile.TemporaryDirectory(prefix="font-pack-") as temporary:
        source = Path(temporary)
        for command in (
            ["git", "init", "-q", str(source)],
            ["git", "-C", str(source), "remote", "add", "origin", lock["repository"]],
            [
                "git",
                "-C",
                str(source),
                "fetch",
                "-q",
                "--depth",
                "1",
                "origin",
                lock["revision"],
            ],
            ["git", "-C", str(source), "checkout", "-q", "--detach", "FETCH_HEAD"],
        ):
            subprocess.run(command, check=True)
        revision = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        if revision != lock["revision"]:
            raise RuntimeError("Unexpected font-pack revision")
        install(
            source,
            Path("/usr/share/fonts/opensiddur-pack"),
            Path("/usr/share/doc/opensiddur-font-pack"),
            lock,
        )
    subprocess.run(["fc-cache", "-f"], check=True)
