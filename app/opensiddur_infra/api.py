import io
import json
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, ValidationError

from .builds import Builds, Rejected, TERMINAL
from .config import Config
from .dispatch import Dispatcher
from .identity import Accounts, FirebaseVerifier
from .processor import Processor
from .storage import Storage
from .store import FirestoreStore


def create_app(
    config=None,
    store=None,
    verifier=None,
    processor=None,
    storage=None,
    dispatcher=None,
):
    config = config or Config()
    store = store or FirestoreStore(config.project)
    accounts = Accounts(store, verifier or FirebaseVerifier())
    processor = processor or Processor(config)
    builds = Builds(store, config.release)
    dispatcher = dispatcher or Dispatcher(config, store)
    app = FastAPI(title="Open Siddur Builder", docs_url=None, redoc_url=None)
    app.state.builds, app.state.store = builds, store

    def objects():
        nonlocal storage
        if storage is None:
            storage = Storage(config)
        return storage

    @app.exception_handler(Rejected)
    async def rejected(request, exc):
        return JSONResponse(
            {"detail": str(exc)},
            status_code=exc.status,
            headers={"Retry-After": "60"} if exc.status in (429, 503) else {},
        )

    @app.middleware("http")
    async def headers(request, call_next):
        if (
            request.method in {"POST", "PUT", "PATCH"}
            and request.url.path != "/api/v1/assets"
        ):
            if len(await request.body()) > 262144:
                return JSONResponse(
                    {"detail": "Settings request exceeds 256 KiB"}, status_code=413
                )
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            }
        )
        return response

    def authenticated(request: Request):
        token = request.headers.get("Authorization", "")
        if not token.startswith("Bearer "):
            raise HTTPException(401, "Sign in to continue")
        try:
            principal = accounts.authenticate(token[7:])
            request.state.principal = principal
            return principal
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(401, "Authentication failed") from None

    def compute(request: Request, principal=Depends(authenticated)):
        # Operators may exercise the private pilot before general submissions open.
        if not config.enabled:
            claims = accounts.verifier.verify(request.headers["Authorization"][7:])
            if claims.get("email") not in config.admins:
                raise HTTPException(503, "The builder is in a private pilot")
        account = store.get(f"account:{principal.account_id}")
        if (account.get("consent") or {}).get("version") != config.consent_version:
            raise HTTPException(
                403, "Consent to the current processing notice is required"
            )
        if config.app_check:
            try:
                from firebase_admin import app_check

                app_check.verify_token(request.headers.get("X-Firebase-AppCheck", ""))
            except Exception:
                raise HTTPException(403, "Application verification required") from None
        return principal

    def internal(request: Request):
        try:
            from google.auth.transport.requests import Request as GoogleRequest
            from google.oauth2.id_token import verify_oauth2_token

            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            claims = verify_oauth2_token(
                token, GoogleRequest(), audience=config.audience
            )
            if claims.get("email") != config.dispatcher_email or not claims.get(
                "email_verified"
            ):
                raise ValueError()
        except Exception:
            raise HTTPException(401, "Internal authentication required") from None

    def validate(data):
        try:
            return processor.validate(data)
        except ValidationError as exc:
            raise HTTPException(
                422,
                [{"path": list(e["loc"]), "message": e["msg"]} for e in exc.errors()],
            ) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    def owned_asset(owner, asset):
        if asset:
            row = store.get(f"asset:{asset}")
            if not row or row["owner"] != owner:
                raise HTTPException(422, "Logo not found")

    def public_build(build):
        return {
            k: v
            for k, v in build.items()
            if k
            in {
                "id",
                "release",
                "state",
                "stage",
                "created",
                "finished",
                "expires",
                "results",
                "formats",
                "type",
                "seconds",
                "elapsed",
                "cancel",
            }
        } | {
            "artifacts": [
                {k: a[k] for k in ("name", "size", "content_type")}
                for a in build["artifacts"]
            ]
        }

    @app.get("/api/v1/health")
    def health():
        return {"ok": True, "release": config.release}

    @app.get("/api/v1/catalog")
    def catalog():
        return processor.catalog()

    @app.get("/api/v1/schema")
    def schema():
        return processor.schema()

    @app.get("/api/v1/notices")
    def notices():
        return json.loads((Path(config.bundle) / "notices.json").read_text())

    @app.get("/api/v1/account")
    def account(principal=Depends(authenticated)):
        row = store.get(f"account:{principal.account_id}")
        from datetime import datetime, timezone

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        full = store.get(f"quota:{principal.account_id}:{day}:full") or {
            "counts": {},
            "seconds": 0,
        }
        preview_quota = store.get(f"quota:{principal.account_id}:{day}:preview") or {
            "counts": {},
            "seconds": 0,
        }
        return {
            "allowances": {
                "builds_remaining": max(0, 5 - full["counts"].get("full", 0)),
                "build_seconds_remaining": max(0, 10800 - full["seconds"]),
                "preview_seconds_remaining": max(0, 1200 - preview_quota["seconds"]),
                "pdf_samples_remaining": max(
                    0, 10 - preview_quota["counts"].get("pdf", 0)
                ),
            },
            "id": principal.account_id,
            "consent": row.get("consent"),
            "consent_version": config.consent_version,
            "submissions_enabled": config.enabled,
        }

    @app.post("/api/v1/consent")
    def consent(data: dict, principal=Depends(authenticated)):
        if data.get("version") != config.consent_version:
            raise HTTPException(409, "Privacy notice changed; reload before consenting")
        key = f"account:{principal.account_id}"

        def accept(values):
            values[key]["consent"] = {
                "version": config.consent_version,
                "at": time.time(),
            }

        store.atomic([key], accept)
        return {"ok": True}

    @app.post("/api/v1/validate")
    def validation(data: dict, principal=Depends(compute)):
        return {"settings": validate(data)}

    class Submission(BaseModel):
        release: str
        settings: dict
        formats: list[str] = Field(min_length=1, max_length=4)
        idempotency_key: str = Field(min_length=1, max_length=100)
        type: str = "full"
        asset: str | None = None

    @app.post("/api/v1/builds", status_code=202)
    def submit(data: Submission, principal=Depends(compute)):
        if data.release != config.release:
            raise HTTPException(
                409, "The catalog changed; reload and validate your settings"
            )
        if len(set(data.formats)) != len(data.formats) or set(data.formats) - {
            "pdf",
            "html",
            "tex",
            "xml",
        }:
            raise HTTPException(422, "Unknown output format")
        owned_asset(principal.account_id, data.asset)
        settings = validate(data.settings)
        build = builds.submit(
            principal.account_id,
            settings,
            data.formats,
            data.type,
            data.idempotency_key,
            data.asset,
        )
        key = f"build:{build['id']}"

        # Persist release-specific destinations before dispatch: a promotion cannot retarget queued work.
        def destinations(values):
            values[key].setdefault("job", config.job)
            values[key].setdefault("preview_url", config.preview_url)

        store.atomic([key], destinations)
        try:
            dispatcher.enqueue(build["id"])
        except Exception:
            pass  # Durable queued record is the outbox; scheduled reconciliation retries.
        return public_build(build)

    @app.get("/api/v1/builds")
    def history(principal=Depends(authenticated)):
        return [
            public_build(b)
            for b in store.list("build", principal.account_id)
            if b.get("expires", float("inf")) > time.time()
        ]

    @app.get("/api/v1/builds/{identifier}")
    def status(identifier: uuid.UUID, principal=Depends(authenticated)):
        return public_build(builds.get(principal.account_id, str(identifier)))

    @app.post("/api/v1/builds/{identifier}/cancel")
    def cancel(identifier: uuid.UUID, principal=Depends(authenticated)):
        return public_build(builds.cancel(principal.account_id, str(identifier)))

    @app.post("/api/v1/builds/{identifier}/share")
    def share(identifier: uuid.UUID, data: dict, principal=Depends(authenticated)):
        token = builds.share(
            principal.account_id, str(identifier), data.get("enabled") is True
        )
        return {"token": token}

    def download(build, name, shared=False, redirect=True):
        artifact = next((a for a in build["artifacts"] if a["name"] == name), None)
        if not artifact or (shared and not name.endswith((".pdf", ".html"))):
            raise HTTPException(404, "Artifact not found")
        url = objects().url(
            artifact["object"], build["expires"], artifact["content_type"]
        )
        return RedirectResponse(url, 303) if redirect else {"url": url}

    @app.get("/api/v1/builds/{identifier}/files/{name}")
    def artifact(
        identifier: uuid.UUID,
        name: str,
        redirect: bool = True,
        principal=Depends(authenticated),
    ):
        return download(
            builds.get(principal.account_id, str(identifier)), name, redirect=redirect
        )

    @app.get("/api/v1/builds/{identifier}/preview")
    def preview(identifier: uuid.UUID, principal=Depends(authenticated)):
        build = builds.get(principal.account_id, str(identifier))
        if build["type"] not in {"html", "pdf"}:
            raise HTTPException(404)
        filename = "book.pdf" if build["type"] == "pdf" else "preview.html"
        item = next((a for a in build["artifacts"] if a["name"] == filename), None)
        if not item:
            raise HTTPException(404)
        return Response(
            objects().read(item["object"]),
            media_type="application/pdf" if build["type"] == "pdf" else "text/html",
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:",
            },
        )

    @app.get("/api/v1/shares/{token}")
    def shared(token: uuid.UUID):
        build = builds.shared(str(token))
        return {
            "id": build["id"],
            "expires": build["expires"],
            "artifacts": [
                {"name": a["name"], "size": a["size"]}
                for a in build["artifacts"]
                if a["name"].endswith((".pdf", ".html"))
            ],
        }

    @app.get("/api/v1/shares/{token}/files/{name}")
    def shared_file(token: uuid.UUID, name: str):
        return download(builds.shared(str(token)), name, shared=True)

    @app.post("/api/v1/assets", status_code=201)
    async def upload(request: Request, principal=Depends(compute)):
        from PIL import Image, ImageOps

        if int(request.headers.get("content-length", "0")) > 5 * 1024**2:
            raise HTTPException(413, "Logo exceeds 5 MiB")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 5 * 1024**2:
                raise HTTPException(413, "Logo exceeds 5 MiB")
        try:
            image = Image.open(io.BytesIO(content))
            if (
                image.format not in {"PNG", "JPEG"}
                or image.width * image.height > 16_000_000
            ):
                raise ValueError()
            image.load()
            image = ImageOps.exif_transpose(image).convert("RGBA")
            image.info.clear()
            output = io.BytesIO()
            image.save(output, format="PNG")
        except Exception:
            raise HTTPException(
                422, "Choose a PNG/JPEG logo under 16 megapixels"
            ) from None
        owner = principal.account_id
        if len(store.list("asset", owner)) >= 50:
            raise HTTPException(429, "Remove unused logos before uploading more")
        identifier = str(uuid.uuid4())
        object_name = f"assets/{identifier}/logo.png"
        objects().put(object_name, output.getvalue(), "image/png")
        key = f"asset:{identifier}"
        store.atomic(
            [key],
            lambda rows: rows.update(
                {
                    key: {
                        "kind": "asset",
                        "id": identifier,
                        "owner": owner,
                        "object": object_name,
                        "created": time.time(),
                    }
                }
            ),
        )
        return {"id": identifier}

    @app.get("/api/v1/presets")
    def presets(principal=Depends(authenticated)):
        return store.list("preset", principal.account_id)

    @app.put("/api/v1/presets/{identifier}")
    def save_preset(identifier: uuid.UUID, data: dict, principal=Depends(compute)):
        key = f"preset:{identifier}"
        existing = store.get(key)
        if existing and existing["owner"] != principal.account_id:
            raise HTTPException(404)
        if not existing and len(store.list("preset", principal.account_id)) >= 50:
            raise HTTPException(429, "Preset limit reached")
        owned_asset(principal.account_id, data.get("asset"))
        settings = validate(data.get("settings", {}))
        preferences = data.get("preferences", {})
        if not isinstance(preferences, dict):
            raise HTTPException(422, "Preset preferences must be a mapping")
        advanced = preferences.get("advanced", False)
        formats = preferences.get("formats", ["pdf", "html"])
        if (
            not isinstance(advanced, bool)
            or not isinstance(formats, list)
            or any(
                not isinstance(f, str) or f not in {"pdf", "html", "tex", "xml"}
                for f in formats
            )
        ):
            raise HTTPException(422, "Invalid preset display or output preferences")
        row = {
            "kind": "preset",
            "id": str(identifier),
            "owner": principal.account_id,
            "name": str(data.get("name", "Untitled"))[:200],
            "settings": settings,
            "release": config.release,
            "asset": data.get("asset"),
            "preferences": {
                "advanced": advanced,
                "formats": list(dict.fromkeys(formats)),
            },
        }
        account_key = f"account:{principal.account_id}"

        def persist(rows):
            account = rows[account_key]
            if not account or not account.get("enabled") or not account.get("consent"):
                raise HTTPException(403, "Hosted processing consent withdrawn")
            rows[key] = row

        store.atomic([key, account_key], persist)
        return row

    @app.delete("/api/v1/presets/{identifier}")
    def delete_preset(identifier: uuid.UUID, principal=Depends(authenticated)):
        key = f"preset:{identifier}"
        row = store.get(key)
        if not row or row["owner"] != principal.account_id:
            raise HTTPException(404)
        store.atomic([key], lambda rows: rows.update({key: None}))
        return {"ok": True}

    @app.get("/api/v1/account/export")
    def export(principal=Depends(authenticated)):
        return {
            kind: store.list(kind, principal.account_id)
            for kind in ("account", "preset", "build", "asset")
        }

    def erase_build(owner, identifier):
        row = builds.cancel(owner, identifier)
        key = f"build:{identifier}"
        old_share = row.get("share_hash")
        keys = [key] + ([f"share:{old_share}"] if old_share else [])

        def erase(rows):
            rows[key]["deleted"] = True
            rows[key]["expires"] = time.time()
            if old_share:
                rows[f"share:{old_share}"] = None

        store.atomic(keys, erase)
        objects().delete_prefix(f"builds/{identifier}/")

    @app.delete("/api/v1/builds/{identifier}")
    def delete_build(identifier: uuid.UUID, principal=Depends(authenticated)):
        erase_build(principal.account_id, str(identifier))
        return {"ok": True}

    @app.delete("/api/v1/consent")
    def withdraw(principal=Depends(authenticated)):
        key = f"account:{principal.account_id}"
        store.atomic([key], lambda rows: rows[key].update(consent=None))
        for row in store.list("build", principal.account_id):
            if row.get("expires", float("inf")) > time.time():
                erase_build(principal.account_id, row["id"])
        for row in store.list("preset", principal.account_id):
            k = f"preset:{row['id']}"
            store.atomic([k], lambda rows: rows.update({k: None}))
        for row in store.list("asset", principal.account_id):
            objects().delete_prefix(f"assets/{row['id']}/")
            key = f"asset:{row['id']}"
            store.atomic([key], lambda rows, key=key: rows.update({key: None}))
        return {"ok": True}

    @app.delete("/api/v1/account")
    def delete_account(principal=Depends(authenticated)):
        if time.time() - principal.authenticated_at > 300:
            raise HTTPException(401, "Sign in again before deleting your account")
        withdraw(principal)
        key = f"account:{principal.account_id}"
        store.atomic(
            [key],
            lambda rows: rows[key].update(
                enabled=False, expires=time.time() + 30 * 86400
            ),
        )
        for row in store.list("identity", principal.account_id):
            accounts.verifier.delete(row["issuer"], row["subject"])
            identity_key = f"identity:{row['id']}"
            store.atomic([identity_key], lambda rows: rows.update({identity_key: None}))
        return {"ok": True}

    @app.post("/internal/dispatch", dependencies=[Depends(internal)])
    def dispatch(data: dict):
        row = store.get(f"build:{data['id']}")
        if not row or row["state"] in TERMINAL or row["cancel"]:
            return {"ok": True}
        if row.get("dispatch") and time.time() - row["dispatch"] < 120:
            return {"ok": True}
        dispatcher.launch(row)
        builds.update(row["id"], dispatch=time.time())
        return {"ok": True}

    @app.post("/internal/reconcile", dependencies=[Depends(internal)])
    def reconcile():
        from .maintenance import reconcile as maintain

        return maintain(config, store, builds, objects(), dispatcher)

    return app


def production_app():
    return create_app()
