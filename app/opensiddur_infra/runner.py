"""Run upstream CLI with an execution-private SQLite index, without modifying upstream."""

import os
import runpy
import sys
from pathlib import Path


def main():
    from opensiddur.exporter.refdb import ReferenceDatabase

    # Upstream binds this path as a Python default at import time. Each runner is a
    # fresh subprocess; replacing that one default cannot affect another build.
    ReferenceDatabase.__init__.__defaults__ = (Path(os.environ["REFERENCE_DB"]),)
    module = sys.argv.pop(1)
    sys.argv[0] = module
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()
