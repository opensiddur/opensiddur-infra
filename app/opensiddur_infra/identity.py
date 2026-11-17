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

    @staticmethod
    def initialize():
        import firebase_admin

        if not firebase_admin._apps:
            firebase_admin.initialize_app()

    def verify(self, token):
        from firebase_admin import auth

        self.initialize()
        claims = auth.verify_id_token(token, check_revoked=True)
        if not claims.get("email_verified"):
            raise ValueError("A verified email is required")
        return claims

    def delete(self, issuer, subject):
        from firebase_admin import auth

        self.initialize()

        try:
            auth.delete_user(subject)
        except auth.UserNotFoundError:
            pass

    def profile(self, identities):
        from firebase_admin import auth

        self.initialize()
        profiles = []
        for identity in identities:
            user = auth.get_user(identity["subject"])
            profiles.append(
                {
                    "uid": user.uid,
                    "email": user.email,
                    "email_verified": user.email_verified,
                    "display_name": user.display_name,
                    "photo_url": user.photo_url,
                    "phone_number": user.phone_number,
                    "disabled": user.disabled,
                    "created_at": user.user_metadata.creation_timestamp,
                    "last_sign_in_at": user.user_metadata.last_sign_in_timestamp,
                    "last_refresh_at": user.user_metadata.last_refresh_timestamp,
                    "tokens_valid_after": user.tokens_valid_after_timestamp,
                    "tenant_id": user.tenant_id,
                    "custom_claims": user.custom_claims,
                    "providers": [
                        {
                            "provider_id": p.provider_id,
                            "uid": p.uid,
                            "email": p.email,
                            "display_name": p.display_name,
                            "photo_url": p.photo_url,
                            "phone_number": p.phone_number,
                        }
                        for p in user.provider_data
                    ],
                }
            )
        return profiles


class Accounts:
    def __init__(self, store, verifier):
        self.store, self.verifier = store, verifier

    def authenticate(self, token, allow_disabled=False):
        claims = self.verifier.verify(token)
        issuer, subject = claims["iss"], claims["sub"]
        identity = hashlib.sha256(f"{issuer}\0{subject}".encode()).hexdigest()
        key = f"identity:{identity}"
        account_id = str(uuid.uuid4())
        account_key = f"account:{account_id}"

        def resolve(values):
            if values[key]:
                return values[key]["owner"]
            # Recheck on transaction retries so an in-flight sign-in cannot
            # recreate an identity after account erasure removed it.
            self.verifier.verify(token)
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

        existing = self.store.get(key)
        account_id = (
            existing["owner"]
            if existing
            else self.store.atomic([key, account_key], resolve)
        )
        account = self.store.get(f"account:{account_id}")
        if not account or (not account["enabled"] and not allow_disabled):
            raise ValueError("Account unavailable")
        return Principal(account_id, issuer, subject, claims.get("auth_time", 0))
