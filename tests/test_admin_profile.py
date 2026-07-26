import unittest
from datetime import datetime
from unittest.mock import Mock

from storage.mongo_store import MongoStore


class AdminProfileStorageTests(unittest.TestCase):
    def setUp(self):
        self.store = MongoStore.__new__(MongoStore)
        self.store.admin_users = Mock()

    def test_get_admin_user_returns_only_public_profile_fields(self):
        self.store.admin_users.find_one.return_value = {
            "_id": "private-object-id",
            "admin_id": "ADM1",
            "name": "Ayesha Khan",
            "username": "ayesha",
            "password_hash": "must-not-leak",
            "password_salt": "must-not-leak",
            "profile_picture": "data:image/png;base64,abc",
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 2),
        }

        result = self.store.get_admin_user(username="AYESHA")

        self.assertEqual(result["admin_id"], "ADM1")
        self.assertEqual(result["profile_picture"], "data:image/png;base64,abc")
        self.assertNotIn("password_hash", result)
        self.assertNotIn("password_salt", result)
        self.store.admin_users.find_one.assert_called_once_with(
            {"username": "ayesha"}
        )

    def test_update_admin_user_returns_updated_profile(self):
        current = {
            "_id": "admin-object-id",
            "admin_id": "ADM1",
            "name": "Old Name",
            "username": "oldname",
        }
        updated = {
            **current,
            "name": "New Name",
            "username": "newname",
            "updated_at": datetime(2026, 2, 1),
        }
        self.store.admin_users.find_one.side_effect = [current, updated]

        result = self.store.update_admin_user(
            current_username="oldname",
            name="New Name",
            username="newname",
        )

        self.assertEqual(result["name"], "New Name")
        self.assertEqual(result["username"], "newname")
        update = self.store.admin_users.update_one.call_args.args[1]["$set"]
        self.assertEqual(update["name"], "New Name")
        self.assertEqual(update["username"], "newname")

    def test_profile_picture_update_preserves_private_credentials(self):
        current = {
            "_id": "admin-object-id",
            "admin_id": "ADM1",
            "name": "Ayesha Khan",
            "username": "ayesha",
            "password_hash": "private",
        }
        updated = {
            **current,
            "profile_picture": "data:image/webp;base64,picture",
        }
        self.store.admin_users.find_one.side_effect = [current, updated]

        result = self.store.set_admin_profile_picture(
            username="ayesha",
            profile_picture="data:image/webp;base64,picture",
        )

        self.assertEqual(
            result["profile_picture"],
            "data:image/webp;base64,picture",
        )
        self.assertNotIn("password_hash", result)


if __name__ == "__main__":
    unittest.main()
