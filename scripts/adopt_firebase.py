"""Import an operator-added Firebase project before Terraform resumes provisioning."""

import subprocess
import sys
import requests

project, config = sys.argv[1:]
existing = subprocess.run(
    [
        "terraform",
        "-chdir=infrastructure",
        "state",
        "show",
        "google_firebase_project.default",
    ],
    capture_output=True,
)
token = subprocess.check_output(
    ["gcloud", "auth", "print-access-token"], text=True
).strip()
response = requests.get(
    f"https://firebase.googleapis.com/v1beta1/projects/{project}",
    headers={"Authorization": "Bearer " + token, "X-Goog-User-Project": project},
    timeout=60,
)
if response.status_code == 200 and existing.returncode != 0:
    subprocess.run(
        [
            "terraform",
            "-chdir=infrastructure",
            "import",
            f"-var-file={config}",
            "google_firebase_project.default",
            project,
        ],
        check=True,
    )

site = subprocess.run(
    [
        "terraform",
        "-chdir=infrastructure",
        "state",
        "show",
        "google_firebase_hosting_site.default",
    ],
    capture_output=True,
)
if site.returncode != 0:
    response = requests.get(
        f"https://firebasehosting.googleapis.com/v1beta1/projects/{project}/sites/{project}",
        headers={"Authorization": "Bearer " + token, "X-Goog-User-Project": project},
        timeout=60,
    )
    if response.status_code == 200:
        subprocess.run(
            [
                "terraform",
                "-chdir=infrastructure",
                "import",
                f"-var-file={config}",
                "google_firebase_hosting_site.default",
                f"projects/{project}/sites/{project}",
            ],
            check=True,
        )
