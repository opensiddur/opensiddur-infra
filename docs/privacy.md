# Privacy responsibilities and retention

The GCP account is personally owned by the operator acting for a fiscally sponsored US project. That fact alone does not identify the controller. Before worldwide registration, agree with the fiscal sponsor who determines purposes and means, publish the controller/contact, document Article 6 and Article 9 bases, assess risk/DPIA requirements and EU/UK representative obligations, and review the Google/Firebase processing and international-transfer arrangements. This document describes engineering behavior; it is not a determination of legal compliance.

Treat linked settings and artifacts as potentially revealing religious beliefs. Use only managed authentication, no passwords stored by the application, and a separate internal account UUID. No ad or behavioral analytics integrations are included. Authentication is US processed; application resources initially use us-central1. The generated `/privacy` page is a private-pilot draft until the operator supplies the required identity/legal details.

## Data lifecycle

| Category | Retention |
|---|---|
| Unsaved browser settings | Current browser session/memory |
| Full build inputs, artifacts, history | 30 days after terminal completion |
| Previews | At most 24 hours |
| Unreferenced logo uploads | 24 hours |
| Explicit saved presets and associated logos | Until deleted |
| Quota/idempotency records | Approximately 32 days |
| Redacted application logs | 30 days |
| Account/consent record | Account lifetime; account closure disables it pending final cleanup |

Expiry is checked on every access before asynchronous physical cleanup. Storage lifecycle is a backstop and not an exact-time deletion guarantee. Soft deletion and versioning are disabled on disposable artifacts. Terraform state is protected/versioned and contains infrastructure configuration, not settings or build outputs. Cloud-required audit logs and service/provider recovery copies have separate provider retention rules; do not promise they disappear immediately.

Users can export their application data, delete individual builds/presets, withdraw consent, and delete their account. Revocation stops new hosted processing and cancels builds. Deletion removes access first and prevents workers from republishing. Share links are opt-in and revocable but downloaded copies cannot be recalled. Signed download URLs may remain valid for five minutes after revocation.

No email addresses, YAML, rendered book text, sign-in tokens or share tokens are intentionally emitted to application logs. Share URLs are excluded from Cloud Run request log storage. Do not enable verbose HTTP/SDK logging in production.

Operational access should use MFA and least privilege, with named administrators and documented access/deletion/incident procedures. Account deletion and legal erasure requests need an operator follow-up mechanism for exceptional provider-held records. The launch review must define consent-evidence retention, children’s access policy, transfer notices and complaint routes rather than assuming nonprofit status removes these duties.
