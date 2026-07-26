import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const FALLBACK_GREETING =
  "السلام علیکم! میں شفا ہسپتال کا وائس اسسٹنٹ ہوں۔ آپ ڈاکٹر کی دستیابی یا اپائنٹمنٹ کے بارے میں بتا سکتے ہیں۔";

function base64ToAudioUrl(base64, mimeType = "audio/mpeg") {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: mimeType });
  return URL.createObjectURL(blob);
}

function speakWithBrowser(text) {
  return new Promise((resolve) => {
    if (!text || !("speechSynthesis" in window)) {
      resolve();
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "ur-PK";
    utterance.rate = 1.05;
    const voices = window.speechSynthesis.getVoices();
    const urduVoice = voices.find((voice) => voice.lang?.toLowerCase().startsWith("ur"));
    if (urduVoice) utterance.voice = urduVoice;
    utterance.onend = resolve;
    utterance.onerror = resolve;
    window.speechSynthesis.speak(utterance);
  });
}

export default function VoiceAgent({ onBack = null }) {
  const recognitionRef = useRef(null);
  const audioRef = useRef(null);
  const sessionIdRef = useRef(null);
  const listeningRef = useRef(false);
  const busyRef = useRef(false);
  const startingRef = useRef(false);
  const recognitionActiveRef = useRef(false);
  const pausedForAgentRef = useRef(false);
  const chatRef = useRef(null);
  const microphoneStreamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const recordingChunksRef = useRef([]);
  const recordingStartedAtRef = useRef(null);
  const audioContextRef = useRef(null);
  const recordingDestinationRef = useRef(null);
  const [isListening, setIsListening] = useState(false);
  const [liveText, setLiveText] = useState("");
  const [status, setStatus] = useState("Idle");
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const supported = useMemo(() => Boolean(SpeechRecognition), []);

  useEffect(() => {
    const chat = chatRef.current;
    if (!chat) return;

    const frame = window.requestAnimationFrame(() => {
      chat.scrollTo({
        top: chat.scrollHeight,
        behavior: history.length > 1 ? "smooth" : "auto",
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [history, status]);

  function startRecognition() {
    if (!recognitionRef.current || recognitionActiveRef.current) return;
    try {
      recognitionRef.current.start();
      recognitionActiveRef.current = true;
    } catch {
      recognitionActiveRef.current = false;
    }
  }

  function stopRecognition() {
    if (!recognitionRef.current || !recognitionActiveRef.current) return;
    try {
      recognitionRef.current.stop();
    } catch {
      recognitionActiveRef.current = false;
    }
  }

  function resumeListeningIfNeeded() {
    if (!listeningRef.current || pausedForAgentRef.current || busyRef.current) return;
    setStatus("Listening");
    startRecognition();
  }

  function playAudio(audioUrl) {
    return new Promise((resolve) => {
      audioRef.current?.pause();
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      const audioContext = audioContextRef.current;
      const recordingDestination = recordingDestinationRef.current;
      if (audioContext && recordingDestination && audioContext.state !== "closed") {
        audioContext.resume().catch(() => {});
        try {
          const source = audioContext.createMediaElementSource(audio);
          source.connect(audioContext.destination);
          source.connect(recordingDestination);
        } catch {
          // Audio still plays normally if browser mixing is unavailable.
        }
      }
      let finished = false;

      const finish = () => {
        if (finished) return;
        finished = true;
        if (audioRef.current === audio) audioRef.current = null;
        URL.revokeObjectURL(audioUrl);
        resolve();
      };

      audio.onended = finish;
      audio.onerror = finish;
      audio.onpause = finish;
      audio.play().catch(finish);
    });
  }

  async function startCallRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      throw new Error("This browser does not support call recording.");
    }

    const microphoneStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      microphoneStream.getTracks().forEach((track) => track.stop());
      throw new Error("This browser does not support audio mixing.");
    }

    const audioContext = new AudioContextClass();
    await audioContext.resume();
    const destination = audioContext.createMediaStreamDestination();
    const microphoneSource = audioContext.createMediaStreamSource(microphoneStream);
    microphoneSource.connect(destination);

    const preferredMimeTypes = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
    ];
    const mimeType = preferredMimeTypes.find((type) => MediaRecorder.isTypeSupported(type));
    const recorder = new MediaRecorder(
      destination.stream,
      mimeType ? { mimeType } : undefined,
    );

    recordingChunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data?.size) recordingChunksRef.current.push(event.data);
    };
    microphoneStreamRef.current = microphoneStream;
    audioContextRef.current = audioContext;
    recordingDestinationRef.current = destination;
    mediaRecorderRef.current = recorder;
    recordingStartedAtRef.current = performance.now();
    recorder.start(1000);
  }

  async function finishCallRecording(sessionId) {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;
    mediaRecorderRef.current = null;
    const durationSeconds = recordingStartedAtRef.current
      ? (performance.now() - recordingStartedAtRef.current) / 1000
      : undefined;
    recordingStartedAtRef.current = null;

    const recordingBlob = await new Promise((resolve) => {
      recorder.onstop = () => {
        resolve(
          new Blob(recordingChunksRef.current, {
            type: recorder.mimeType || "audio/webm",
          }),
        );
      };
      if (recorder.state === "inactive") {
        recorder.onstop();
      } else {
        recorder.stop();
      }
    });

    microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
    microphoneStreamRef.current = null;
    recordingDestinationRef.current = null;
    recordingChunksRef.current = [];
    const audioContext = audioContextRef.current;
    audioContextRef.current = null;
    if (audioContext && audioContext.state !== "closed") {
      await audioContext.close();
    }

    if (sessionId && recordingBlob.size) {
      try {
        await api.uploadCallRecording(sessionId, recordingBlob, durationSeconds);
      } catch (err) {
        setError(err.message || "Failed to save the call recording");
      }
    }
  }

  async function handleTurn(finalTranscript) {
    if (!finalTranscript || busyRef.current) return;
    const turnSessionId = sessionIdRef.current;
    let conversationEnded = false;
    const messageTime = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    setHistory((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: finalTranscript,
        time: messageTime,
      },
    ]);
    busyRef.current = true;
    pausedForAgentRef.current = true;
    stopRecognition();
    setBusy(true);
    setStatus("Processing");
    setError("");

    try {
      const resp = await api.postTextTurn({
        transcript: finalTranscript,
        session_id: turnSessionId,
        // Use the configured cloud TTS because browser Urdu voices are not
        // consistently installed or available on Windows.
        return_tts: true,
      });

      // Stop is a true toggle: a response that arrives after this call was
      // stopped must not update the UI or begin speaking.
      if (!listeningRef.current || sessionIdRef.current !== turnSessionId) return;

      if (resp.assistant_text) {
        setHistory((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "agent",
            content: resp.assistant_text,
            time: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
            intent: resp.intent?.intent || "other",
          },
        ]);
      }

      if (resp.tts_audio_base64) {
        const audioUrl = base64ToAudioUrl(resp.tts_audio_base64, resp.audio_mime);
        setStatus("AI Speaking");
        await playAudio(audioUrl);
      } else if (resp.assistant_text) {
        setStatus("AI Speaking");
        await speakWithBrowser(resp.assistant_text);
      }

      if (resp.conversation_ended) {
        conversationEnded = true;
        const endedSessionId = sessionIdRef.current;
        listeningRef.current = false;
        pausedForAgentRef.current = false;
        stopRecognition();
        setIsListening(false);
        await finishCallRecording(endedSessionId);
        sessionIdRef.current = null;
      }
    } catch (err) {
      setError(err.message || "Failed to process voice turn");
    } finally {
      busyRef.current = false;
      pausedForAgentRef.current = false;
      setBusy(false);
      setLiveText("");
      if (conversationEnded) {
        setStatus("Ended");
      } else if (listeningRef.current) {
        resumeListeningIfNeeded();
      } else {
        setStatus("Idle");
      }
    }
  }

  async function startListening() {
    if (!supported || busy || startingRef.current) return;
    startingRef.current = true;
    setBusy(true);
    setError("");
    try {
      await startCallRecording();
    } catch (err) {
      setError(err.message || "Unable to start call recording");
      startingRef.current = false;
      setBusy(false);
      return;
    }

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
        recognitionActiveRef.current = false;
        resumeListeningIfNeeded();
      };

      recognition.onerror = () => {
        setError("Speech recognition error. Check microphone permission.");
      };

      recognitionRef.current = recognition;
    }

    // Start defines a new call. Every utterance until Stop shares this ID.
    sessionIdRef.current = `session-${Date.now()}-${crypto.randomUUID()}`;
    setHistory([]);
    setLiveText("");
    listeningRef.current = true;
    pausedForAgentRef.current = true;
    busyRef.current = true;
    setIsListening(true);
    setStatus("AI Speaking");

    let greetingText = FALLBACK_GREETING;
    try {
      const greeting = await api.getVoiceGreeting();
      if (!listeningRef.current) return;
      greetingText = greeting.assistant_text || FALLBACK_GREETING;
      setHistory([
        {
          id: crypto.randomUUID(),
          role: "agent",
          content: greetingText,
          time: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          intent: "greeting",
        },
      ]);

      if (greeting.tts_audio_base64) {
        const audioUrl = base64ToAudioUrl(
          greeting.tts_audio_base64,
          greeting.audio_mime,
        );
        await playAudio(audioUrl);
      } else {
        await speakWithBrowser(greetingText);
      }
    } catch {
      if (!listeningRef.current) return;
      setHistory([
        {
          id: crypto.randomUUID(),
          role: "agent",
          content: greetingText,
          time: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          intent: "greeting",
        },
      ]);
      await speakWithBrowser(greetingText);
    } finally {
      pausedForAgentRef.current = false;
      busyRef.current = false;
      startingRef.current = false;
      setBusy(false);
      if (listeningRef.current) {
        setStatus("Listening");
        startRecognition();
      }
    }
  }

  async function stopListening() {
    window.speechSynthesis?.cancel();
    audioRef.current?.pause();
    audioRef.current = null;
    pausedForAgentRef.current = false;
    listeningRef.current = false;
    stopRecognition();
    setIsListening(false);
    setStatus("Idle");
    const completedSessionId = sessionIdRef.current;
    sessionIdRef.current = null;
    await finishCallRecording(completedSessionId);
    if (completedSessionId) {
      try {
        await api.completeSession(completedSessionId);
      } catch (err) {
        setError(err.message || "Failed to complete call session");
      }
    }
  }

  async function returnToModuleSelection() {
    if (isListening) {
      await stopListening();
    }
    onBack?.();
  }

  return (
    <div>
      <div className="voiceAgentPageHeader">
        <div>
          <div className="h1">Live Voice Agent</div>
          <div className="small">Speak in real time. The agent replies with text and voice.</div>
        </div>
        {onBack && (
          <button className="btn btnGhost voiceAgentBackButton" type="button" onClick={returnToModuleSelection}>
            <span aria-hidden="true">←</span> Back
          </button>
        )}
      </div>

      {!supported && (
        <div className="card cardPad mt16">
          This browser does not support SpeechRecognition. Use Chrome/Edge.
        </div>
      )}

      <div className="voiceAgentWorkspace">
        <div className="voiceAgentLeftColumn">
          <div className="card cardPad voicePanel">
            <div className="voiceOrbControl">
              <button
                className={`voiceOrbButton ${isListening ? "voiceOrbActive" : ""}`}
                type="button"
                onClick={isListening ? stopListening : startListening}
                disabled={!supported || (!isListening && busy)}
                aria-label={isListening ? "Stop voice agent" : "Start voice agent"}
                aria-pressed={isListening}
              >
                <span className="voiceOrbSurface" aria-hidden="true" />
                <svg
                  className="voiceOrbMicrophone"
                  viewBox="0 0 64 64"
                  aria-hidden="true"
                >
                  <rect x="23" y="8" width="18" height="34" rx="9" />
                  <path d="M15 31v3c0 9.4 7.6 17 17 17s17-7.6 17-17v-3" />
                  <path d="M32 51v8" />
                  <path d="M24 59h16" />
                </svg>
              </button>
              <div className="voiceOrbHint">
                {isListening ? "Tap to stop" : "Tap to start"}
              </div>
            </div>
            <div className="voiceOrbStatus small" aria-live="polite">
              Status: <strong>{status}</strong>
            </div>
            {error && <div className="small" style={{ color: "#b91c1c" }}>{error}</div>}
          </div>

          <div className="card cardPad voiceTranscriptCard">
            <div className="cardTitle">Live Transcript</div>
            <div className="voiceBox urduText mt12" dir="auto">
              {liveText || "Listening transcript appears here..."}
            </div>
          </div>
        </div>

        <div className="card conversationCard voiceAgentHistoryColumn">
          <div className="conversationHeader">
            <div>
              <div className="cardTitle">Conversation History</div>
              <div className="small">Live patient and agent messages</div>
            </div>
            <div className={`chatStatus ${isListening ? "chatStatusLive" : ""}`}>
              <span className="chatStatusDot" aria-hidden="true" />
              {isListening ? "Live" : "Offline"}
            </div>
          </div>

          <div
            ref={chatRef}
            className="voiceHistory"
            role="log"
            aria-live="polite"
            aria-label="Live conversation"
          >
            {history.length === 0 && status !== "Processing" && (
              <div className="chatEmpty">
                <div className="chatEmptyIcon" aria-hidden="true">AI</div>
                <div className="chatEmptyTitle">No conversation yet</div>
                <div className="small">Start the voice agent to see messages here.</div>
              </div>
            )}

            {history.map((message) => (
              <div
                key={message.id}
                className={`chatMessageRow ${message.role === "user" ? "chatMessageUser" : "chatMessageAgent"}`}
              >
                <div className="chatMessageGroup">
                  <div className="chatMessageMeta">
                    <span>{message.role === "user" ? "Patient" : "AI Agent"}</span>
                    <span aria-hidden="true">&bull;</span>
                    <time>{message.time}</time>
                    {message.intent && <span className="chatIntent">{message.intent.replaceAll("_", " ")}</span>}
                  </div>
                  <div className="chatBubble urduText" dir="auto">{message.content}</div>
                </div>
              </div>
            ))}

            {status === "Processing" && (
              <div className="chatMessageRow chatMessageAgent chatTypingRow">
                <div className="chatMessageGroup">
                  <div className="chatMessageMeta">AI Agent</div>
                  <div className="chatBubble chatTyping" aria-label="AI Agent is typing">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
