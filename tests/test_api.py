import io
import time
import unittest
import uuid
from dataclasses import replace

from fastapi.testclient import TestClient
from PIL import Image

from opensiddur_infra.api import create_app
from opensiddur_infra.config import Config
from opensiddur_infra.store import MemoryStore


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

    def delete(self, token):
        pass


class Processor:
    def catalog(self):
        return {"release": "test", "projects": []}

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
        self.client.post("/api/v1/consent", headers=self.headers)

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

    def test_authentication_and_public_catalog(self):
        self.assertEqual(self.client.get("/api/v1/catalog").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/builds").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/v1/builds", headers={"Authorization": "Bearer bad"}
            ).status_code,
            401,
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
