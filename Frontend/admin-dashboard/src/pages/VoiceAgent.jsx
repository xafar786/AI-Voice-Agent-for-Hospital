import { useMemo, useRef, useState } from "react";
import { api } from "../api/client";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

function base64ToAudioUrl(base64, mimeType = "audio/mpeg") {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: mimeType });
  return URL.createObjectURL(blob);
}

export default function VoiceAgent() {
  const recognitionRef = useRef(null);
  const sessionIdRef = useRef(`session-${Date.now()}`);
  const listeningRef = useRef(false);
  const [isListening, setIsListening] = useState(false);
  const [liveText, setLiveText] = useState("");
  const [lastResponse, setLastResponse] = useState("");
  const [status, setStatus] = useState("Idle");
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const supported = useMemo(() => Boolean(SpeechRecognition), []);

  async function handleTurn(finalTranscript) {
    if (!finalTranscript || busy) return;
    setBusy(true);
    setStatus("Processing");
    setError("");

    try {
      const resp = await api.postTextTurn({
        transcript: finalTranscript,
        session_id: sessionIdRef.current,
        return_tts: true,
      });

      setLastResponse(resp.assistant_text || "");
      setHistory((prev) => [
        {
          user: finalTranscript,
          ai: resp.assistant_text || "",
          intent: resp.intent?.intent || "other",
        },
        ...prev,
      ]);

      if (resp.tts_audio_base64) {
        const audioUrl = base64ToAudioUrl(resp.tts_audio_base64, resp.audio_mime);
        const audio = new Audio(audioUrl);
        audio.onended = () => URL.revokeObjectURL(audioUrl);
        audio.play().catch(() => URL.revokeObjectURL(audioUrl));
      }
    } catch (err) {
      setError(err.message || "Failed to process voice turn");
    } finally {
      setBusy(false);
      setStatus(isListening ? "Listening" : "Idle");
      setLiveText("");
    }
  }

  function startListening() {
    if (!supported || busy) return;
    if (!recognitionRef.current) {
      const recognition = new SpeechRecognition();
      recognition.lang = "ur-PK";
      recognition.interimResults = true;
      recognition.continuous = true;

      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const transcript = event.results[i][0]?.transcript || "";
          if (event.results[i].isFinal) {
            handleTurn(transcript.trim());
          } else {
            interim += transcript;
          }
        }
        setLiveText(interim.trim());
      };

      recognition.onend = () => {
        if (listeningRef.current) recognition.start();
      };

      recognition.onerror = () => {
        setError("Speech recognition error. Check microphone permission.");
      };

      recognitionRef.current = recognition;
    }

    recognitionRef.current.start();
    listeningRef.current = true;
    setIsListening(true);
    setStatus("Listening");
  }

  function stopListening() {
    recognitionRef.current?.stop();
    listeningRef.current = false;
    setIsListening(false);
    setStatus("Idle");
  }

  return (
    <div>
      <div className="h1">Live Voice Agent</div>
      <div className="small">Speak in real time. The agent replies with text and voice.</div>

      {!supported && (
        <div className="card cardPad mt16">
          This browser does not support SpeechRecognition. Use Chrome/Edge.
        </div>
      )}

      <div className="mt16 card cardPad voicePanel">
        <div className="voiceButtons">
          <button className="btn btnPrimary" onClick={startListening} disabled={!supported || isListening || busy}>
            Start
          </button>
          <button className="btn" onClick={stopListening} disabled={!isListening}>
            Stop
          </button>
        </div>
        <div className="small">Status: {status}</div>
        {error && <div className="small" style={{ color: "#b91c1c" }}>{error}</div>}
      </div>

      <div className="mt16 grid2">
        <div className="card cardPad">
          <div className="cardTitle">Live Transcript</div>
          <div className="voiceBox mt12">{liveText || "Listening transcript appears here..."}</div>
        </div>
        <div className="card cardPad">
          <div className="cardTitle">Latest AI Response</div>
          <div className="voiceBox mt12">{lastResponse || "AI response appears here..."}</div>
        </div>
      </div>

      <div className="mt16 card cardPad">
        <div className="cardTitle">Conversation History</div>
        <div className="mt12 voiceHistory">
          {history.length === 0 && <div className="small">No conversation yet.</div>}
          {history.map((item, index) => (
            <div key={`${item.user}-${index}`} className="voiceItem">
              <div className="small"><strong>User:</strong> {item.user}</div>
              <div className="small"><strong>AI:</strong> {item.ai}</div>
              <div className="small"><strong>Intent:</strong> {item.intent}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
