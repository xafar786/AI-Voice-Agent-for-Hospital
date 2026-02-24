import base64
from io import BytesIO
import wave

def synthesize_tts_base64(text: str) -> tuple[str, str]:
    # Generate a short silent WAV clip as a local placeholder (no external TTS API).
    frame_rate = 16000
    duration_seconds = 0.4
    num_frames = int(frame_rate * duration_seconds)

    with BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(frame_rate)
            silence_frame = (0).to_bytes(2, byteorder="little", signed=True)
            wav_file.writeframes(silence_frame * num_frames)
        audio_bytes = buffer.getvalue()

    return base64.b64encode(audio_bytes).decode("utf-8"), "audio/wav"
