def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    if not audio_bytes:
        return ""
    return "Audio message received."
