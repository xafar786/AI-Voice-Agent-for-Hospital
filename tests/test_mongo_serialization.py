from bson import ObjectId

from storage.mongo_store import MongoStore


def test_call_log_serialization_converts_mongodb_object_ids():
    document_id = ObjectId()
    recording_id = ObjectId()

    result = MongoStore._serialize_call_log(
        {
            "_id": document_id,
            "session_id": "session-1",
            "recording_file_id": recording_id,
        }
    )

    assert result["id"] == str(document_id)
    assert result["recording_file_id"] == str(recording_id)
    assert "_id" not in result
