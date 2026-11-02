"""Cancel only builder executions before removing their runtime resources."""

import subprocess
import sys
import time
import requests

project, region = sys.argv[1:]
token = subprocess.check_output(
    ["gcloud", "auth", "print-access-token"], text=True
).strip()
headers = {"Authorization": "Bearer " + token, "X-Goog-User-Project": project}
base = f"https://run.googleapis.com/v2/projects/{project}/locations/{region}"
response = requests.get(base + "/jobs", headers=headers, timeout=60)
response.raise_for_status()
for job in response.json().get("jobs", []):
    if not job["name"].rsplit("/", 1)[-1].startswith("builder-"):
        continue
    response = requests.get(
        "https://run.googleapis.com/v2/" + job["name"] + "/executions",
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()
    for execution in response.json().get("executions", []):
        if execution.get("completionTime"):
            continue
        endpoint = "https://run.googleapis.com/v2/" + execution["name"]
        requests.post(
            endpoint + ":cancel", headers=headers, json={}, timeout=60
        ).raise_for_status()
        for _ in range(60):
            result = requests.get(endpoint, headers=headers, timeout=60)
            result.raise_for_status()
            if result.json().get("completionTime"):
                break
            time.sleep(2)
        else:
            raise SystemExit("Execution did not stop; refusing runtime teardown")
