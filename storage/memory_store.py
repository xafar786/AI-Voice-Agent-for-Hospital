from typing import Dict, Any

class MemoryStore:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get(self, session_id: str) -> Dict[str, Any]:
        return self.sessions.setdefault(session_id, {"history": []})

    def append(self, session_id: str, role: str, content: str):
        s = self.get(session_id)
        s["history"].append({"role": role, "content": content})