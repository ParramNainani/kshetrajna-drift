import http.client
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path

from app import create_server
from drift import Organizer


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.root = cls.base / "files"
        cls.root.mkdir()
        cls.org = Organizer(cls.root, cls.base / "journal.db")
        cls.server = create_server(cls.org, port=0, demo=True)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", cls.port)
        connection.request("GET", "/")
        response = connection.getresponse()
        cls.token = re.search(r'name="drift-token" content="([^"]+)"', response.read().decode()).group(1)
        connection.close()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.org.db.close()
        cls.temp.cleanup()

    def request(self, method, path, body=None, auth=True, origin=True, host=None):
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["X-Drift-Token"] = self.token
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{self.port}"
        if host:
            headers["Host"] = host
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
        response = connection.getresponse()
        status, data, response_headers = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return status, data, response_headers

    def test_api_requires_session(self):
        self.assertEqual(self.request("GET", "/api/state", auth=False)[0], 403)

    def test_mutation_requires_origin(self):
        self.assertEqual(self.request("POST", "/api/scan", {}, origin=False)[0], 403)

    def test_host_check_rejects_rebinding(self):
        self.assertEqual(self.request("GET", "/", host="attacker.example")[0], 403)

    def test_state_and_content_policy(self):
        status, raw, headers = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["demo"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_scan_is_read_only(self):
        status, raw, _ = self.request("POST", "/api/scan", {})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["files"], [])

    def test_bad_payload_is_rejected(self):
        self.assertEqual(self.request("POST", "/api/plan", ["invalid"])[0], 400)
        self.assertEqual(self.request("POST", "/api/undo", {"id": True})[0], 400)

    def test_plan_needs_a_model(self):
        self.assertEqual(self.request("POST", "/api/plan", {})[0], 400)

    def test_static_path_is_allowlisted(self):
        self.assertEqual(self.request("GET", "/../drift.py")[0], 404)
        self.assertEqual(self.request("GET", "/app.js")[0], 200)


if __name__ == "__main__":
    unittest.main()
