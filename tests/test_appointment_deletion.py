import unittest
from unittest.mock import Mock

from bson import ObjectId

from storage.mongo_store import MongoStore


class AppointmentDeletionTests(unittest.TestCase):
    def test_delete_appointment_by_mongodb_id(self):
        appointment_id = ObjectId()
        store = object.__new__(MongoStore)
        store.appointments = Mock()
        store.appointments.delete_one.return_value.deleted_count = 1

        self.assertTrue(store.delete_appointment(str(appointment_id)))
        store.appointments.delete_one.assert_called_once_with({"_id": appointment_id})

    def test_delete_appointment_by_external_id(self):
        store = object.__new__(MongoStore)
        store.appointments = Mock()
        store.appointments.delete_one.return_value.deleted_count = 1

        self.assertTrue(store.delete_appointment("apt13"))
        store.appointments.delete_one.assert_called_once_with({"appointment_id": "APT13"})

    def test_delete_missing_appointment_returns_false(self):
        store = object.__new__(MongoStore)
        store.appointments = Mock()
        store.appointments.delete_one.return_value.deleted_count = 0

        self.assertFalse(store.delete_appointment("APT999"))


if __name__ == "__main__":
    unittest.main()
