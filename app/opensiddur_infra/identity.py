import hashlib
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    account_id: str
    issuer: str
    subject: str
    authenticated_at: int


class FirebaseVerifier:
    """Provider adapter. Application records never depend on Firebase's UID."""

    def verify(self, token):
        import firebase_admin
        from firebase_admin import auth

        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        claims = auth.verify_id_token(token, check_revoked=True)
        if not claims.get("email_verified"):
            raise ValueError("A verified email is required")
        return claims

    def delete(self, subject):
        from firebase_admin import auth

        auth.delete_user(subject)


class Accounts:
    def __init__(self, store, verifier):
        self.store, self.verifier = store, verifier

    def authenticate(self, token):
        claims = self.verifier.verify(token)
        issuer, subject = claims["iss"], claims["sub"]
        identity = hashlib.sha256(f"{issuer}\0{subject}".encode()).hexdigest()
        key = f"identity:{identity}"
        account_id = str(uuid.uuid4())
        account_key = f"account:{account_id}"

        def resolve(values):
            if values[key]:
                return values[key]["owner"]
            values[key] = {
                "kind": "identity",
                "id": identity,
                "owner": account_id,
                "issuer": issuer,
                "subject": subject,
            }
            values[account_key] = {
                "kind": "account",
                "owner": account_id,
                "id": account_id,
                "enabled": True,
                "consent": None,
            }
            return account_id

        account_id = self.store.atomic([key, account_key], resolve)
        account = self.store.get(f"account:{account_id}")
        if not account or not account["enabled"]:
            raise ValueError("Account unavailable")
        return Principal(account_id, issuer, subject, claims.get("auth_time", 0))
