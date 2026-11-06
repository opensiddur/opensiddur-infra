import io
import time
import unittest
import uuid
from dataclasses import replace

from fastapi.testclient import TestClient
from opensiddur_infra.api import create_app
from opensiddur_infra.config import Config
from opensiddur_infra.store import MemoryStore
from PIL import Image


class Verifier:
    def verify(self, token):
        if token == "bad":
            raise ValueError()
        return {
            "iss": "https://securetoken.google.com/test",
            "sub": token,
            "email_verified": True,
            "email": "user@example.test",
            "auth_time": time.time(),
        }

    def delete(self, issuer, token):
        pass


class Processor:
    def catalog(self):
        return {
            "release": "test",
            "projects": [{"id": "synthetic", "title": "Synthetic Prayerbook"}],
        }

    def schema(self):
        return {"type": "object"}

    def validate(self, settings):
        if settings.get("invalid"):
            raise ValueError("Invalid synthetic settings")
        return settings


class Objects:
    def __init__(self):
        self.data = {}

    def put(self, name, data, content_type, **kwargs):
        self.data[name] = data
        return {
            "name": name.split("/")[-1],
            "object": name,
            "size": len(data),
            "content_type": content_type,
        }

    def read(self, name):
        return self.data[name]

    def delete_prefix(self, prefix):
        self.data = {k: v for k, v in self.data.items() if not k.startswith(prefix)}

    def url(self, *args):
        return "https://storage.example.test/temporary"


class Dispatcher:
    def enqueue(self, identifier):
        pass


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.store, self.objects = MemoryStore(), Objects()
        config = replace(Config(), release="test", enabled=True, app_check=False)
        self.app = create_app(
            config, self.store, Verifier(), Processor(), self.objects, Dispatcher()
        )
        self.client = TestClient(self.app)
        self.headers = {"Authorization": "Bearer owner"}
        self.client.get("/api/v1/account", headers=self.headers)
        self.client.post(
            "/api/v1/consent",
            headers=self.headers,
            json={"version": config.consent_version},
        )

    def submit(self):
        response = self.client.post(
            "/api/v1/builds",
            headers=self.headers,
            json={
                "release": "test",
                "settings": {"book": {"project": "synthetic"}},
                "formats": ["pdf", "html"],
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def test_history_is_newest_first_and_resolves_legacy_work_titles(self):
        owner = self.client.get("/api/v1/account", headers=self.headers).json()["id"]
        rows = {
            "build:older": {
                "kind": "build",
                "owner": owner,
                "id": "older",
                "created": 10,
                "settings": {"book": {"project": "synthetic"}},
                "artifacts": [],
            },
            "build:newer": {
                "kind": "build",
                "owner": owner,
                "id": "newer",
                "created": 30,
                "title": "Saved work title",
                "settings": {"book": {"project": "synthetic"}},
                "artifacts": [],
            },
            "build:someone-else": {
                "kind": "build",
                "owner": "other-account",
                "id": "someone-else",
                "created": 40,
                "title": "Private other work",
                "artifacts": [],
            },
        }
        self.store.atomic(list(rows), lambda values: values.update(rows))
        response = self.client.get("/api/v1/builds", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(row["id"], row["title"]) for row in response.json()],
            [("newer", "Saved work title"), ("older", "Synthetic Prayerbook")],
        )

    def test_new_build_records_the_work_title(self):
        result = self.submit()
        self.assertEqual(result["title"], "Synthetic Prayerbook")
        self.assertEqual(
            self.store.get("build:" + result["id"])["title"], "Synthetic Prayerbook"
        )

    def test_authentication_and_public_catalog(self):
        self.assertEqual(self.client.get("/api/v1/catalog").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/builds").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/v1/builds", headers={"Authorization": "Bearer bad"}
            ).status_code,
            401,
        )

    def test_private_pdf_preview_and_allowance(self):
        response = self.client.post(
            "/api/v1/builds",
            headers=self.headers,
            json={
                "release": "test",
                "settings": {"book": {"project": "synthetic"}},
                "formats": ["pdf"],
                "type": "pdf",
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 202, response.text)
        row = response.json()
        artifact = self.objects.put(
            "builds/private/book.pdf", b"%PDF-synthetic", "application/pdf"
        )
        self.app.state.builds.finish(row["id"], "succeeded", artifacts=[artifact])
        path = "/api/v1/builds/" + row["id"] + "/preview"
        result = self.client.get(path, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.content, b"%PDF-synthetic")
        self.assertEqual(result.headers["content-type"], "application/pdf")
        self.assertEqual(result.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(
            self.client.get(
                path, headers={"Authorization": "Bearer other"}
            ).status_code,
            404,
        )
        allowance = self.client.get("/api/v1/account", headers=self.headers).json()[
            "allowances"
        ]
        self.assertEqual(allowance["pdf_samples_remaining"], 9)
        self.assertEqual(
            allowance["samples"],
            {"html": {"used": 0, "limit": 300}, "pdf": {"used": 1, "limit": 10}},
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/builds/" + self.submit()["id"] + "/preview",
                headers=self.headers,
            ).status_code,
            404,
        )

    def test_private_running_log_download_and_share_exclusion(self):
        row = self.submit()
        artifact = self.objects.put(
            "builds/private/worker.log", b"Private synthetic log", "text/plain"
        )
        self.app.state.builds.update(row["id"], artifacts=[artifact])
        path = "/api/v1/builds/" + row["id"] + "/files/worker.log?redirect=false"
        self.assertEqual(self.client.get(path, headers=self.headers).status_code, 200)
        self.assertEqual(
            self.client.get(
                path, headers={"Authorization": "Bearer other"}
            ).status_code,
            404,
        )
        self.app.state.builds.finish(row["id"], "partial", artifacts=[artifact])
        token = self.client.post(
            "/api/v1/builds/" + row["id"] + "/share",
            headers=self.headers,
            json={"enabled": True},
        ).json()["token"]
        self.assertEqual(
            self.client.get("/api/v1/shares/" + token).json()["artifacts"], []
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/shares/" + token + "/files/worker.log"
            ).status_code,
            404,
        )

    def test_cross_account_access_denied(self):
        row = self.submit()
        response = self.client.get(
            "/api/v1/builds/" + row["id"], headers={"Authorization": "Bearer other"}
        )
        self.assertEqual(response.status_code, 404)

    def test_download_does_not_leak_owner_or_settings(self):
        row = self.submit()
        self.app.state.builds.finish(
            row["id"],
            "succeeded",
            artifacts=[
                {
                    "name": "book.pdf",
                    "object": "builds/private/book.pdf",
                    "size": 10,
                    "content_type": "application/pdf",
                },
                {
                    "name": "settings.yaml",
                    "object": "builds/private/settings.yaml",
                    "size": 10,
                    "content_type": "text/yaml",
                },
            ],
        )
        share = self.client.post(
            "/api/v1/builds/" + row["id"] + "/share",
            headers=self.headers,
            json={"enabled": True},
        ).json()["token"]
        response = self.client.get("/api/v1/shares/" + share)
        self.assertNotIn("owner", response.json())
        self.assertEqual(
            [a["name"] for a in response.json()["artifacts"]], ["book.pdf"]
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/shares/" + share + "/files/settings.yaml"
            ).status_code,
            404,
        )
        response = self.client.get(
            "/api/v1/builds/" + row["id"] + "/files/book.pdf?redirect=false",
            headers=self.headers,
        )
        self.assertIn("url", response.json())

    def test_logo_is_reencoded_and_foreign_assets_rejected(self):
        image = io.BytesIO()
        Image.new("RGB", (2, 2)).save(image, "JPEG", comment=b"private metadata")
        response = self.client.post(
            "/api/v1/assets", headers=self.headers, content=image.getvalue()
        )
        self.assertEqual(response.status_code, 201, response.text)
        stored = next(iter(self.objects.data.values()))
        self.assertTrue(stored.startswith(b"\x89PNG"))
        self.assertNotIn(b"private metadata", stored)
        self.assertEqual(
            self.client.post(
                "/api/v1/assets", headers=self.headers, content=b"<svg/>"
            ).status_code,
            422,
        )

    def test_withdrawal_revokes_share_and_prevents_new_work(self):
        row = self.submit()
        self.app.state.builds.finish(row["id"], "succeeded")
        token = self.client.post(
            "/api/v1/builds/" + row["id"] + "/share",
            headers=self.headers,
            json={"enabled": True},
        ).json()["token"]
        self.assertEqual(
            self.client.delete("/api/v1/consent", headers=self.headers).status_code, 200
        )
        self.assertEqual(self.client.get("/api/v1/shares/" + token).status_code, 404)
        response = self.client.post(
            "/api/v1/builds",
            headers=self.headers,
            json={
                "release": "test",
                "settings": {},
                "formats": ["pdf"],
                "idempotency_key": "new",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_saved_presets_are_owner_scoped(self):
        identifier = str(uuid.uuid4())
        response = self.client.put(
            "/api/v1/presets/" + identifier,
            headers=self.headers,
            json={"name": "My book", "settings": {}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/v1/presets", headers={"Authorization": "Bearer other"}
            ).json(),
            [],
        )
        self.assertEqual(
            self.client.delete(
                "/api/v1/presets/" + identifier,
                headers={"Authorization": "Bearer other"},
            ).status_code,
            404,
        )

    def test_presets_remember_advanced_mode_and_output_choices(self):
        identifier = str(uuid.uuid4())
        response = self.client.put(
            "/api/v1/presets/" + identifier,
            headers=self.headers,
            json={
                "name": "Layout",
                "settings": {},
                "preferences": {"advanced": True, "formats": ["html", "tex"]},
            },
        )
        self.assertEqual(response.status_code, 200)
        saved = self.client.get("/api/v1/presets", headers=self.headers).json()
        self.assertEqual(
            saved[0]["preferences"], {"advanced": True, "formats": ["html", "tex"]}
        )
        invalid = self.client.put(
            "/api/v1/presets/" + identifier,
            headers=self.headers,
            json={"settings": {}, "preferences": {"advanced": "false"}},
        )
        self.assertEqual(invalid.status_code, 422)

    def test_server_processing_requires_consent_not_just_a_disabled_button(self):
        self.client.delete("/api/v1/consent", headers=self.headers)
        self.assertEqual(
            self.client.post(
                "/api/v1/validate", headers=self.headers, json={}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.put(
                "/api/v1/presets/" + str(uuid.uuid4()),
                headers=self.headers,
                json={"settings": {}},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/assets", headers=self.headers, content=b"image"
            ).status_code,
            403,
        )

    def test_request_size_limit_applies_before_validation(self):
        response = self.client.post(
            "/api/v1/validate", headers=self.headers, json={"title": "x" * 300000}
        )
        self.assertEqual(response.status_code, 413)
