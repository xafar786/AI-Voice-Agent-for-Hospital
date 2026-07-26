from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import tempfile

from config import ASR_MODEL_DIR


def get_asr_status() -> dict[str, str]:
    model_dir = Path(ASR_MODEL_DIR)
    required_files = ["config.json", "model.safetensors", "preprocessor_config.json"]
    missing_files = [name for name in required_files if not (model_dir / name).exists()]

    if not model_dir.exists():
        return {"status": "Down", "detail": f"ASR model folder not found: {model_dir}"}
    if missing_files:
        return {"status": "Down", "detail": f"Missing ASR files: {', '.join(missing_files)}"}

    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as exc:
        return {"status": "Down", "detail": f"Missing dependency: {exc.name}"}

    if _get_asr_pipeline.cache_info().currsize:
        return {"status": "Active", "detail": "ASR model is loaded and ready."}
    return {"status": "Ready", "detail": "ASR model files and dependencies are available."}


@lru_cache(maxsize=1)
def _get_asr_pipeline():
    try:
        import torch
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError(
            "ASR dependencies are not installed. Run `pip install -r requirements.txt`."
        ) from exc

    model_dir = Path(ASR_MODEL_DIR)
    if not model_dir.exists():
        raise RuntimeError(f"ASR model directory was not found: {model_dir}")

    device = 0 if torch.cuda.is_available() else -1
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    return pipeline(
        "automatic-speech-recognition",
        model=str(model_dir),
        tokenizer=str(model_dir),
        feature_extractor=str(model_dir),
        device=device,
        torch_dtype=torch_dtype,
    )


def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    if not audio_bytes:
        return ""

    suffix = Path(filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as temp_audio:
        temp_audio.write(audio_bytes)
        temp_audio.flush()
        result = _get_asr_pipeline()(temp_audio.name)

    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    return str(result or "").strip()
