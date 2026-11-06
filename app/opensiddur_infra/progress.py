"""Small, content-free progress records and bounded private diagnostic logs."""

import copy
from pathlib import Path


def build_steps(kind, formats):
    outputs = (
        [kind]
        if kind in {"html", "pdf"}
        else sorted(
            formats, key=lambda value: {"html": 0, "xml": 1, "tex": 2, "pdf": 3}[value]
        )
    )
    steps = [{"id": "prepare", "label": "Prepare settings", "state": "pending"}]
    seen = set()
    for output in outputs:
        destination = "electronic" if output == "html" and kind == "full" else "print"
        if destination not in seen:
            steps.append(
                {
                    "id": "compile-" + destination,
                    "label": f"Compile {destination} text",
                    "state": "pending",
                }
            )
            seen.add(destination)
        steps.append(
            {
                "id": output,
                "label": {
                    "html": "Render HTML",
                    "xml": "Export XML",
                    "tex": "Render TeX",
                    "pdf": "Typeset PDF",
                }[output],
                "state": "pending",
            }
        )
    return steps + [
        {"id": "package", "label": "Package downloads", "state": "pending"},
        {"id": "upload", "label": "Publish files", "state": "pending"},
    ]


class Progress:
    def __init__(self, builds, identifier, steps):
        self.builds, self.identifier, self.steps = (
            builds,
            identifier,
            copy.deepcopy(steps),
        )
        self.pdf_event = None

    def set(self, identifier, state):
        step = next(item for item in self.steps if item["id"] == identifier)
        step["state"] = state
        self.builds.update(
            self.identifier, stage=step["label"], steps=copy.deepcopy(self.steps)
        )

    def pdf_pass(self, event):
        number = event.get("pass")
        phase = event.get("phase", "typesetting")
        if (
            not isinstance(number, int)
            or not 1 <= number <= 100
            or phase not in {"typesetting", "bibliography"}
        ):
            return
        if (number, phase) == self.pdf_event:
            return
        self.pdf_event = (number, phase)
        step = next(item for item in self.steps if item["id"] == "pdf")
        step.update(pass_number=number, phase=phase)
        self.builds.update(
            self.identifier,
            stage=f"Typeset PDF · pass {number}"
            + (" · bibliography" if phase == "bibliography" else ""),
            steps=copy.deepcopy(self.steps),
        )


def copy_log(source: Path, destination: Path, limit=8 * 1024**2):
    """Keep bounded logs without reading an unbounded TeX log into memory."""
    if not source.is_file():
        return False
    with source.open("rb") as stream:
        if source.stat().st_size <= limit:
            data = stream.read(limit)
        else:
            notice = b"\n\n[Log truncated: beginning and latest output retained.]\n\n"
            head = min(32768, limit // 4)
            data = stream.read(head)
            tail = max(0, limit - head - len(notice))
            stream.seek(-tail, 2)
            data += notice + stream.read(tail)
    destination.write_bytes(data)
    return True
