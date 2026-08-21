from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.ui.web_dashboard.contracts import WebDashboardPolicy
from src.ui.web_dashboard.controller import WebDashboardController
from src.ui.web_dashboard.fastapi_app import create_fastapi_app
from src.ui.web_dashboard.frame_store import LatestPresentationFrameStore
from src.ui.web_dashboard.resource_tokens import WebResourceTokenStore
from src.ui.web_dashboard.session_store import InMemoryWebSessionStore


class WebDashboardFastApiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.closing = threading.Event()
        self.store = LatestPresentationFrameStore()
        self.controller = WebDashboardController(lambda: None)
        policy = WebDashboardPolicy(
            True, "127.0.0.1", 8080, False, False, 2, 75, 1
        )
        self.app = create_fastapi_app(
            policy,
            self.controller,
            self.store,
            closing=self.closing,
            streams=threading.BoundedSemaphore(1),
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.store.close()

    def test_serves_spa_and_api_with_security_headers(self):
        page = self.client.get("/")
        dashboard = self.client.get("/api/dashboard")

        self.assertEqual(page.status_code, 200)
        self.assertIn('<div id="root">', page.text)
        self.assertEqual(dashboard.status_code, 200)
        self.assertFalse(dashboard.json()["available"])
        self.assertEqual(page.headers["x-content-type-options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", page.headers["content-security-policy"])

    def test_mutation_requires_same_origin_expiring_csrf_session(self):
        denied = self.client.post(
            "/api/presentation/ignore", json={}, headers={"Origin": "http://testserver"}
        )
        session = self.client.get("/api/session").json()
        accepted = self.client.post(
            "/api/presentation/ignore",
            json={},
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": session["csrf_token"],
            },
        )
        foreign = self.client.post(
            "/api/presentation/ignore",
            json={},
            headers={
                "Origin": "https://foreign.example",
                "X-CSRF-Token": session["csrf_token"],
            },
        )

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(foreign.status_code, 403)

    def test_controller_enforces_existing_authorization_boundary(self):
        authorization = SimpleNamespace(
            require=lambda _permission: SimpleNamespace(allowed=False)
        )
        controller = WebDashboardController(
            lambda: None, authorization=authorization
        )

        with self.assertRaises(PermissionError):
            controller.api("/api/dashboard")


class InMemoryWebSessionStoreTests(unittest.TestCase):
    def test_sessions_expire_and_oldest_is_evicted_at_capacity(self):
        now = [0.0]
        store = InMemoryWebSessionStore(
            ttl_seconds=5,
            maximum_sessions=1,
            monotonic=lambda: now[0],
        )
        first = store.issue()
        second = store.issue()

        self.assertFalse(store.validate(first.session_id, first.csrf_token))
        self.assertTrue(store.validate(second.session_id, second.csrf_token))
        now[0] = 6.0
        self.assertFalse(store.validate(second.session_id, second.csrf_token))


class WebResourceTokenStoreTests(unittest.TestCase):
    def test_photo_references_are_opaque_and_bounded(self):
        store = WebResourceTokenStore(capacity=1)
        first_url = store.photo_url(
            SimpleNamespace(available=True, image_bytes=b"first", format="JPEG")
        )
        second_url = store.photo_url(
            SimpleNamespace(available=True, image_bytes=b"second", format="PNG")
        )

        self.assertNotIn("first", first_url)
        self.assertIsNone(store.thumbnail(first_url.rsplit("/", 1)[-1]))
        self.assertEqual(
            store.thumbnail(second_url.rsplit("/", 1)[-1]),
            ("image/png", b"second"),
        )


if __name__ == "__main__":
    unittest.main()
