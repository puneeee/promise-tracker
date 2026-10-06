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
from app.main import DataMigration, SessionLocal, app, normalize_legacy_whole_number_targets  # noqa: E402


class PromiseTrackerApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_personal_promise_and_group_invite_smoke_flow(self):
        me = self.client.get("/me")
        self.assertEqual(me.status_code, 200)
        personal_space = me.json()["personal_space_id"]
        profile = self.client.patch("/me", json={"display_name": "API Tester"})
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["display_name"], "API Tester")

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
        personal_comment = self.client.post(f"/promises/{promise_id}/comments", json={"body": "A private note"})
        self.assertEqual(personal_comment.status_code, 201)
        self.assertEqual(self.client.get(f"/promises/{promise_id}/comments").json()[0]["body"], "A private note")

        legacy_target = self.client.post(f"/spaces/{personal_space}/promises", json={
            "title": "Legacy five hour target", "tracking_mode": "duration", "target_value": 5.01, "unit": "hours",
        })
        self.assertEqual(legacy_target.status_code, 201)
        with SessionLocal() as db:
            db.query(DataMigration).filter_by(key="normalize_legacy_whole_number_targets_v1").delete()
            db.commit()
        normalize_legacy_whole_number_targets()
        normalized = self.client.get(f"/spaces/{personal_space}/promises?view=active").json()
        self.assertEqual(next(item for item in normalized if item["id"] == legacy_target.json()["id"])["target_value"], "5.00")
        progress = self.client.post(f"/promises/{promise_id}/progress", json={"value": 3})
        self.assertEqual(progress.status_code, 200)
        history = self.client.get(f"/promises/{promise_id}/history")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["entries"][0]["total"], 3.0)
        edited = self.client.patch(f"/promises/{promise_id}", json={"title": "Walk 12 kilometres", "unit": "km"})
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["title"], "Walk 12 kilometres")
        self.assertEqual(self.client.post(f"/promises/{promise_id}/archive").status_code, 200)
        archived = self.client.get(f"/spaces/{personal_space}/promises?view=archived")
        self.assertTrue(any(item["id"] == promise_id for item in archived.json()))
        self.assertEqual(self.client.post(f"/promises/{promise_id}/restore").status_code, 200)

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

        shared = self.client.post(f"/spaces/{group.json()['space_id']}/promises", json={
            "title": "Run five kilometres together", "tracking_mode": "quantity",
            "target_value": 5, "unit": "km", "shared": True, "shared_member_ids": ["demo-user"],
        })
        self.assertEqual(shared.status_code, 201)
        self.assertTrue(shared.json()["is_shared"])
        self.assertTrue(shared.json()["can_update"])
        mine = self.client.get("/my-promises?view=active")
        self.assertEqual(mine.status_code, 200)
        self.assertTrue(any(item["id"] == shared.json()["id"] and item["space_id"] == group.json()["space_id"] for item in mine.json()))
        self.assertEqual(self.client.post(
            f"/promises/{shared.json()['id']}/progress", json={"value": 5, "note": "Finished together"}
        ).status_code, 200)
        comment = self.client.post(
            f"/promises/{shared.json()['id']}/comments", json={"body": "Great work, team!"}
        )
        self.assertEqual(comment.status_code, 201)
        comments = self.client.get(f"/promises/{shared.json()['id']}/comments")
        self.assertEqual(comments.status_code, 200)
        self.assertEqual(comments.json()[0]["body"], "Great work, team!")


if __name__ == "__main__":
    unittest.main()
