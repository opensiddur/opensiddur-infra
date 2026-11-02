import json
import re
import sys
from pathlib import Path

p = Path(sys.argv[1])
text = p.read_text()
match = re.search(r"^release_images = (.+)$", text, re.M)
images = json.loads(match.group(1)) if match else {}
images[sys.argv[4]] = sys.argv[2]
lines = [
    s
    for s in text.splitlines()
    if not s.startswith(("image =", "api_image =", "release_id =", "release_images ="))
]
lines.extend(
    f"{name} = {json.dumps(value)}"
    for name, value in zip(("image", "api_image", "release_id"), sys.argv[2:])
)
lines.append("release_images = " + json.dumps(images))
p.write_text("\n".join(lines) + "\n")
