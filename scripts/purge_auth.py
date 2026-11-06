import subprocess
import sys
import requests

project = sys.argv[1]
token = subprocess.check_output(
    ["gcloud", "auth", "print-access-token"], text=True
).strip()
headers = {"Authorization": "Bearer " + token, "X-Goog-User-Project": project}
base = f"https://identitytoolkit.googleapis.com/v1/projects/{project}/accounts"
while True:
    response = requests.get(
        base + ":batchGet", headers=headers, params={"maxResults": 1000}, timeout=60
    )
    response.raise_for_status()
    users = response.json().get("users", [])
    if not users:
        break
    response = requests.post(
        base + ":batchDelete",
        headers=headers,
        json={"localIds": [u["localId"] for u in users], "force": True},
        timeout=60,
    )
    response.raise_for_status()
    if response.json().get("errors"):
        raise SystemExit("Some authentication accounts could not be deleted")
