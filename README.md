# AI-Voice-Agent-for-Hospital

## LLM configuration

This project uses OpenAI `gpt-5-nano` for intent classification and natural grounded replies.

Add these values to `.env`:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5-nano
```

Install dependencies with:

```bash
pip install -r requirements.txt
```

## TTS configuration

This project uses OpenAI's cloud Text-to-Speech API with `gpt-4o-mini-tts`.

Add these values to `.env`:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=cedar
OPENAI_TTS_RESPONSE_FORMAT=mp3
OPENAI_TTS_INSTRUCTIONS=Speak naturally in clear Urdu with a calm, helpful hospital appointment assistant tone.
```
