import os
import re
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused"
)
os.environ.setdefault(
    "JWT_SECRET_KEY", "synthetic-test-key-for-hs256-at-least-32-bytes"
)

from app.web.frontend_pages import router as pages_router

PAGES = [route.path for route in pages_router.routes if route.path not in {"/", "/analyst"}]


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "frontend" / "static"


class FrontendPagesTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(pages_router)
        app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
        self.client = TestClient(app)

    def test_pages_render(self):
        for path in PAGES:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
                self.assertIn("/static/js/api.js", response.text)

    def test_retired_analyst_page_returns_404(self):
        self.assertEqual(self.client.get("/analyst").status_code, 404)

    def test_app_entry_redirects_to_login(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login")

    def test_referenced_static_files_exist(self):
        for path in PAGES:
            html = self.client.get(path).text
            for ref in ("/static/css/monitor.css", "/static/js/api.js"):
                self.assertIn(ref, html)
        for name in (
            "css/monitor.css",
            "js/api.js",
            "js/login.js",
            "js/executor.js",
            "js/coordinator.js",
            "js/summary.js",
            "js/insights.js",
            "js/notify.js",
            "js/manager.js",
            "js/admin.js",
        ):
            with self.subTest(file=name):
                self.assertTrue((STATIC / name).is_file())
                self.assertEqual(self.client.get("/static/" + name).status_code, 200)

    def test_all_referenced_static_assets_exist(self):
        for path in PAGES:
            html = self.client.get(path).text
            for ref in re.findall(r'(?:src|href)="(/static/[^"]+)"', html):
                with self.subTest(page=path, asset=ref):
                    self.assertEqual(self.client.get(ref).status_code, 200)

    def test_no_external_resources(self):
        # Закритий контур: сторінки не тягнуть CDN чи зовнішні шрифти.
        for path in PAGES:
            html = self.client.get(path).text
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)


if __name__ == "__main__":
    unittest.main()
