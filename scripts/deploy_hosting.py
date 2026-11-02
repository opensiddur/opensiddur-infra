#!/usr/bin/env python3
"""Firebase Hosting REST deployment using the authenticated gcloud account."""

import concurrent.futures
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import requests

project = sys.argv[1]
token = subprocess.check_output(
    ["gcloud", "auth", "print-access-token"], text=True
).strip()
headers = {"Authorization": "Bearer " + token}
base = "https://firebasehosting.googleapis.com/v1beta1"


def call(method, url, **kwargs):
    response = requests.request(method, url, headers=headers, timeout=120, **kwargs)
    if not response.ok:
        raise SystemExit(f"Hosting API {response.status_code}: {response.text[:1000]}")
    return response.json() if response.content else {}


version = call(
    "POST",
    f"{base}/sites/{project}/versions",
    json=json.loads(Path(".runtime/hosting.json").read_text()),
)
files = {}
compressed = {}
for path in Path("web/dist").rglob("*"):
    if path.is_file():
        data = gzip.compress(path.read_bytes(), mtime=0)
        digest = hashlib.sha256(data).hexdigest()
        files["/" + str(path.relative_to("web/dist"))] = digest
        compressed[digest] = data
upload = call("POST", f"{base}/{version['name']}:populateFiles", json={"files": files})


def send(digest):
    response = requests.post(
        upload["uploadUrl"] + "/" + digest,
        headers=headers | {"Content-Type": "application/octet-stream"},
        data=compressed[digest],
        timeout=120,
    )
    response.raise_for_status()


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(send, upload.get("uploadRequiredHashes", [])))
call(
    "PATCH", f"{base}/{version['name']}?updateMask=status", json={"status": "FINALIZED"}
)
call(
    "POST", f"{base}/sites/{project}/releases", params={"versionName": version["name"]}
)
print(f"https://{project}.web.app")
