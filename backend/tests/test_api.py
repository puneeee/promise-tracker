"""Minimal regression coverage for the public Promise Tracker API."""

import os
import tempfile
import unittest
from pathlib import Path

database_file = Path(tempfile.gettempdir()) / "promise-tracker-api-test.db"
if database_file.exists():
    database_file.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.as_posix()}"
os.environ["APP_ENV"] = "test"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


class PromiseTrackerApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_personal_promise_and_group_invite_smoke_flow(self):
        me = self.client.get("/me")
        self.assertEqual(me.status_code, 200)
        personal_space = me.json()["personal_space_id"]

        missing_unit = self.client.post(f"/spaces/{personal_space}/promises", json={
            "title": "Walk 10 kilometres", "tracking_mode": "quantity", "target_value": 10,
        })
        self.assertEqual(missing_unit.status_code, 422)

        promise = self.client.post(f"/spaces/{personal_space}/promises", json={
            "title": "Walk 10 kilometres", "tracking_mode": "quantity", "target_value": 10, "unit": "km",
        })
        self.assertEqual(promise.status_code, 201)
        self.assertEqual(promise.json()["unit"], "km")

        group = self.client.post("/groups", json={"name": "API test group", "join_policy": "invite_link"})
        self.assertEqual(group.status_code, 201)
        invite = self.client.post(f"/groups/{group.json()['id']}/invites")
        self.assertEqual(invite.status_code, 201)
        joined = self.client.post(f"/invites/{invite.json()['token']}/join")
        self.assertEqual(joined.status_code, 200)
        self.assertEqual(joined.json()["id"], group.json()["id"])


if __name__ == "__main__":
    unittest.main()
