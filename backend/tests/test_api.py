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
        promise_id = promise.json()["id"]
        progress = self.client.post(f"/promises/{promise_id}/progress", json={"value": 3})
        self.assertEqual(progress.status_code, 200)
        history = self.client.get(f"/promises/{promise_id}/history")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["entries"][0]["total"], 3.0)
        edited = self.client.patch(f"/promises/{promise_id}", json={"title": "Walk 12 kilometres", "unit": "km"})
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["title"], "Walk 12 kilometres")

        check_off = self.client.post(f"/spaces/{personal_space}/promises", json={
            "title": "Daily check in", "tracking_mode": "check_off", "frequency": "daily",
        })
        self.assertEqual(check_off.status_code, 201)
        self.assertEqual(self.client.post(f"/promises/{check_off.json()['id']}/progress", json={"value": 1}).status_code, 200)
        self.assertEqual(self.client.post(f"/promises/{check_off.json()['id']}/progress", json={"value": 1}).status_code, 409)

        range_promise = self.client.post(f"/spaces/{personal_space}/promises", json={
            "title": "Finish a short range", "tracking_mode": "quantity", "target_value": 1, "unit": "task",
            "schedule_type": "date_range", "start_date": "2026-01-01", "end_date": "2026-12-31",
        })
        self.assertEqual(self.client.post(f"/promises/{range_promise.json()['id']}/progress", json={"value": 1}).status_code, 200)
        completed = self.client.get(f"/spaces/{personal_space}/promises?view=completed")
        self.assertTrue(any(item["id"] == range_promise.json()["id"] for item in completed.json()))

        group = self.client.post("/groups", json={"name": "API test group", "join_policy": "invite_link"})
        self.assertEqual(group.status_code, 201)
        self.assertEqual(self.client.post("/groups", json={"name": "   ", "join_policy": "invite_link"}).status_code, 422)
        settings = self.client.patch(f"/groups/{group.json()['id']}", json={"name": "Renamed API group", "join_policy": "invite_link", "timezone": "Asia/Kolkata"})
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(settings.json()["name"], "Renamed API group")
        invite = self.client.post(f"/groups/{group.json()['id']}/invites")
        self.assertEqual(invite.status_code, 201)
        joined = self.client.post(f"/invites/{invite.json()['token']}/join")
        self.assertEqual(joined.status_code, 200)
        self.assertEqual(joined.json()["id"], group.json()["id"])


if __name__ == "__main__":
    unittest.main()
