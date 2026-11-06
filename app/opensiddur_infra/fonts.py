"""Inventory the font faces that fontconfig actually resolves in the runtime image."""

import base64
import re
import subprocess
from collections import defaultdict
from pathlib import Path

FORMAT = "%{file}\t%{family}\t%{charset}\n"
HEBREW_LETTERS = set(range(0x05D0, 0x05EB))
VOWELS = set(range(0x05B0, 0x05BD)) | {0x05C1, 0x05C2}
CANTILLATION = set(range(0x0591, 0x05B0))
LATIN = set(range(65, 91)) | set(range(97, 123))
LATIN_FAMILIES = {
    "DejaVu Sans",
    "DejaVu Sans Mono",
    "DejaVu Serif",
    "Liberation Sans",
    "Liberation Serif",
    "Liberation Mono",
    "Linux Libertine O",
    "Linux Libertine Display O",
    "Linux Libertine Mono O",
    "Linux Biolinum O",
    "FreeSerif",
    "FreeSans",
    "FreeMono",
    "Noto Sans",
    "Noto Serif",
    "Noto Sans Mono",
    "Carlito",
    "Caladea",
}
LABELS = {
    3: "Hebrew with vowels and cantillation",
    2: "Hebrew with vowels",
    1: "Hebrew consonants only",
    0: "Partial Hebrew / historical scripts",
}
FONT_TYPES = {".otf": "otf", ".ttf": "ttf", ".ttc": "collection"}
MAX_PREVIEW_FONT_BYTES = 8 * 1024**2


def embed_preview_fonts(preview, settings_file, catalog):
    """Embed installed faces for the HTML renderer's Latin and Hebrew CSS stacks."""
    from opensiddur.exporter.cli_common import load_output_settings
    from opensiddur.exporter.html.css import css_string

    typography = load_output_settings(settings_file, resolve_fonts=False).typography
    names = dict.fromkeys(
        name
        for family in ("latin", "hebrew")
        for name in typography.fonts[family].names
    )
    installed = set(catalog["installed"])
    remaining = MAX_PREVIEW_FONT_BYTES
    rules = []
    for name in names:
        if name not in installed:
            continue
        match = subprocess.check_output(
            ["fc-match", "--format", "%{file}\t%{family}", "--", name], text=True
        )
        file, _, families = match.partition("\t")
        path = Path(file).resolve()
        font_type = FONT_TYPES.get(path.suffix.lower())
        if (
            name not in families.split(",")
            or not font_type
            or not path.is_relative_to("/usr/share/fonts")
            or not path.is_file()
            or path.stat().st_size > remaining
        ):
            continue
        data = path.read_bytes()
        remaining -= len(data)
        encoded = base64.b64encode(data).decode("ascii")
        family = css_string(name).replace("<", r"\3c ")
        rules.append(
            f"@font-face {{ font-family: {family}; "
            f'src: url("data:font/{font_type};base64,{encoded}"); }}'
        )
    if rules:
        html = preview.read_text(encoding="utf-8")
        style = "<style>\n" + "\n".join(rules) + "\n</style>\n"
        preview.write_text(
            html.replace("</head>", style + "</head>", 1), encoding="utf-8"
        )


def covers(charset, points):
    ranges = [
        tuple(int(part, 16) for part in token.split("-")) for token in charset.split()
    ]
    return all(
        any(bounds[0] <= point <= bounds[-1] for bounds in ranges) for point in points
    )


def pack_support(path):
    if "/Hebrew Letters only/" in path:
        return 1
    if "/Hebrew Letters with Vowels (no cantillation)/" in path:
        return 2
    if "/Hebrew Letters with Vowels and Cantillation/" in path:
        return 3
    return None


def inventory():
    rows = subprocess.check_output(
        ["fc-list", "--format", FORMAT], text=True
    ).splitlines()
    candidates, limits = set(), {}
    for row in rows:
        file, families, _ = row.split("\t", 2)
        if Path(file).suffix.lower() not in {".otf", ".ttf", ".ttc"}:
            continue
        if "/Fallback Fonts/" in file:
            continue
        # The first family name is fontconfig's canonical spelling; aliases remain
        # valid to the compiler but do not clutter the chooser with duplicates.
        family = families.split(",")[0].strip()
        if not family or re.search(r"[{}\\%#&$^_~]", family):
            continue  # These names cannot be represented by the compiler's font syntax.
        candidates.add(family)
        support = pack_support(file)
        if support is not None:
            limits[family] = min(limits.get(family, support), support)
    hebrew, latin, other, available = defaultdict(list), [], [], []
    for family in sorted(candidates, key=str.casefold):
        row = subprocess.check_output(
            ["fc-match", "--format", FORMAT, "--", family], text=True
        ).rstrip("\n")
        file, resolved, charset = row.split("\t", 2)
        if not charset:
            continue
        if (
            family.casefold()
            not in {name.strip().casefold() for name in resolved.split(",")}
            or not Path(file).is_file()
        ):
            continue
        if "/Fallback Fonts/" in file or family in {"Adobe Blank", "LastResort"}:
            continue
        available.append(family)
        if covers(charset, HEBREW_LETTERS):
            support = (
                3
                if covers(charset, VOWELS | CANTILLATION)
                else 2
                if covers(charset, VOWELS)
                else 1
            )
            hebrew[min(support, limits.get(family, support))].append(family)
        elif pack_support(file) is not None:
            hebrew[0].append(family)
        else:
            other.append(family)
        if family in LATIN_FAMILIES and covers(charset, LATIN):
            latin.append(family)
    return {
        "installed": available,
        "hebrew": [
            {"label": LABELS[level], "fonts": hebrew[level]}
            for level in (3, 2, 1, 0)
            if hebrew[level]
        ],
        "latin": [{"label": "Installed Latin fonts", "fonts": latin}],
        "other": [{"label": "Other installed fonts", "fonts": other}],
    }
