import json
import os
import sys
from pathlib import Path

project, region = sys.argv[1:]
config = {
    "googleEnabled": os.getenv("GOOGLE_AUTH_ENABLED", "false") == "true",
    "appCheckSiteKey": os.getenv("APP_CHECK_SITE_KEY", ""),
}
Path("web/dist/runtime-config.json").write_text(json.dumps(config))
operator = os.getenv(
    "PRIVACY_OPERATOR", "Operator details are being finalized for the private pilot."
)
contact = os.getenv("PRIVACY_CONTACT", "Public registration is not yet open.")
import html

Path("web/dist/privacy.html").write_text(
    f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Privacy · Open Siddur</title><main style="max-width:750px;margin:4rem auto;font:18px/1.7 system-ui;padding:20px"><a href="/">← Builder</a><h1>Privacy notice</h1><p>Operator: {html.escape(operator)}</p><p>Contact: {html.escape(contact)}</p><p>We use account identity to authenticate you and enforce allowances. Settings may reveal religious beliefs; we process them only after your explicit consent, to generate the books you request. Artifacts, settings for those builds, and history expire 30 days after completion. Previews last at most 24 hours. Presets and associated logos you explicitly save remain until you delete them. Unused uploads expire after 24 hours.</p><p>Builds are private unless you enable sharing. Anyone holding a share link may download the shared PDF or HTML until expiry or revocation. Downloaded copies cannot be recalled. Short-lived download URLs may work for up to five minutes after sharing is revoked.</p><p>We use Google Cloud and Firebase, processing data in the United States, including authentication. We do not sell your settings or use advertising or behavioral analytics. Operational logs omit settings and text and are retained for 30 days. Cloud providers may retain service/security records under their documented policies.</p><p>Use account controls to export your data, delete presets or builds, withdraw processing consent, or delete your account. Access is revoked immediately; physical cleanup is asynchronous. Contact the operator to exercise other applicable privacy rights or make a complaint. This notice must be completed with the controller identity, legal bases, transfer arrangements, applicable rights and supervisory contacts before worldwide registration opens.</p></main></html>"""
)
config = {
    "config": {
        "rewrites": [
            {"glob": "/api/**", "run": {"serviceId": "builder-api", "region": region}},
            {
                "glob": "/internal/**",
                "run": {"serviceId": "builder-api", "region": region},
            },
            {"glob": "/privacy", "path": "/privacy.html"},
            {"glob": "**", "path": "/index.html"},
        ],
        "headers": [
            {
                "glob": "**",
                "headers": {
                    "Referrer-Policy": "no-referrer",
                    "X-Content-Type-Options": "nosniff",
                },
            }
        ],
    }
}
Path(".runtime/hosting.json").write_text(json.dumps(config))
