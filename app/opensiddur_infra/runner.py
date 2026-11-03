"""Run upstream CLI with an execution-private SQLite index, without modifying upstream."""

import importlib
import json
import shutil
import os
import subprocess
import runpy
import sys
from pathlib import Path


def portable_notice_renderer(original, output):
    """Place validated logos beside the TeX file and use a relative TeX path."""

    def render(notice, logo):
        if logo is None:
            return original(notice, logo)
        destination = Path(output).resolve().parent / "logo.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if Path(logo).resolve() != destination:
            shutil.copyfile(logo, destination)
        return original(notice, destination).replace(
            destination.as_posix(), destination.name
        )

    return render


def main():
    from opensiddur.exporter.refdb import ReferenceDatabase

    # Upstream binds this path as a Python default at import time. Each runner is a
    # fresh subprocess; replacing that one default cannot affect another build.
    ReferenceDatabase.__init__.__defaults__ = (Path(os.environ["REFERENCE_DB"]),)
    progress_file = os.environ.get("BUILD_PROGRESS_FILE")
    original_run = subprocess.run
    pass_number = 0

    def observed_run(command, *args, **kwargs):
        nonlocal pass_number
        executable = (
            Path(str(command[0])).name
            if isinstance(command, (list, tuple)) and command
            else ""
        )
        if progress_file and executable in {"lualatex", "bibtex"}:
            if executable == "lualatex":
                pass_number += 1
            path = Path(progress_file)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "pass": pass_number,
                        "phase": "typesetting"
                        if executable == "lualatex"
                        else "bibliography",
                    }
                )
            )
            temporary.replace(path)
        return original_run(command, *args, **kwargs)

    subprocess.run = observed_run
    module = sys.argv.pop(1)
    sys.argv[0] = module
    output_flag = "--tex-output" if module == "opensiddur.exporter.pdf.pdf" else "-o"
    if (
        module in {"opensiddur.exporter.pdf.pdf", "opensiddur.exporter.tex.latex"}
        and output_flag in sys.argv
    ):
        latex = importlib.import_module("opensiddur.exporter.tex.latex")
        output = sys.argv[sys.argv.index(output_flag) + 1]
        latex.distribution_notice_to_tex = portable_notice_renderer(
            latex.distribution_notice_to_tex, output
        )
        importlib.import_module(module).main()
    else:
        runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()
