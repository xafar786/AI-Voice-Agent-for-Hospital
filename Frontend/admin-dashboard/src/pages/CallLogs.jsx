import { useEffect, useMemo, useRef, useState } from "react";
import { api, formatDateTime } from "../api/client";

function StatMini({ title, value, note }) {
  return (
    <div className="card cardPad callStat">
      <div className="small" style={{ fontWeight: 800 }}>{title}</div>
      <div className="statValue" style={{ fontSize: 22 }}>{value}</div>
      <div className="small">{note}</div>
    </div>
  );
}

function shortCallReference(call) {
  const raw = String(call.id || call.session_id || "");
  return raw ? `#${raw.slice(-8).toUpperCase()}` : "—";
}

function callerInitials(name) {
  const normalized = String(name || "").trim();
  if (!normalized || normalized === "Unknown Caller") return "UC";
  return normalized
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function callMessageCount(call) {
  if (call.turns?.length) return call.turns.length * 2;
  return Number(Boolean(call.transcript)) + Number(Boolean(call.assistant_text));
}

export default function CallLogs() {
  const [calls, setCalls] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getCallLogs()
      .then(setCalls)
      .catch((err) => setError(err.message || "Failed to load call logs"))
      .finally(() => setLoading(false));
  }, []);

  const topStats = useMemo(() => {
    const total = calls.length;
    const today = new Date().toDateString();
    const todayCalls = calls.filter((call) => {
      const createdAt = new Date(call.created_at);
      return !Number.isNaN(createdAt.getTime()) && createdAt.toDateString() === today;
    }).length;
    const recordings = calls.filter((call) => call.has_recording).length;
    const messages = calls.reduce((sum, call) => sum + callMessageCount(call), 0);
    return [
      { title: "Total Calls", value: String(total), note: "All recorded conversations" },
      { title: "Calls Today", value: String(todayCalls), note: "Started today" },
      { title: "Recordings", value: String(recordings), note: "Audio available" },
      { title: "Messages", value: String(messages), note: "Patient and agent exchanges" },
    ];
  }, [calls]);

  const filteredCalls = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    if (!query) return calls;
    return calls.filter((call) =>
      [call.id, call.session_id, call.patient_name, call.phone]
        .some((value) => String(value || "").toLowerCase().includes(query))
    );
  }, [calls, searchTerm]);

  if (loading) return <div className="card cardPad">Loading call logs...</div>;
  if (error) return <div className="card cardPad">{error}</div>;

  return (
    <div>
      <div className="spread">
        <div>
          <div className="h1">Call Records & Transcripts</div>
          <div className="small">Review patient conversations and call recordings</div>
        </div>
      </div>

      <div className="mt16 grid4">
        {topStats.map((s) => (
          <StatMini key={s.title} title={s.title} value={s.value} note={s.note} />
        ))}
      </div>

      <div className="mt16 card tableCard">
        <div className="callRecordsToolbar">
          <div>
            <div className="cardTitle">Recent Calls</div>
            <div className="small">
              {filteredCalls.length} {filteredCalls.length === 1 ? "record" : "records"}
            </div>
          </div>
          <input
            className="input callSearch"
            type="search"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search caller, phone, or call reference"
            aria-label="Search call records"
          />
        </div>

        <div className="callRecordsTableWrap">
          <table className="table callRecordsTable">
            <thead>
              <tr>
                <th className="th">Call</th>
                <th className="th">Caller</th>
                <th className="th">Date & Time</th>
                <th className="th">Messages</th>
                <th className="th">Recording</th>
                <th className="th tRight">Details</th>
              </tr>
            </thead>

            <tbody>
              {filteredCalls.map((c) => (
                <tr
                  key={c.id}
                  className="tr callLogRow"
                  tabIndex={0}
                  onClick={() => setSelectedCall(c)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedCall(c);
                    }
                  }}
                >
                  <td className="td">
                    <div className="callReference" title={c.id}>{shortCallReference(c)}</div>
                    <div className="small">Voice call</div>
                  </td>
                  <td className="td">
                    <div className="callerCell">
                      <div className="callerAvatar">{callerInitials(c.patient_name)}</div>
                      <div>
                        <div className="callerName">{c.patient_name || "Unknown Caller"}</div>
                        <div className="small">{c.phone || "Phone not provided"}</div>
                      </div>
                    </div>
                  </td>
                  <td className="td">{formatDateTime(c.created_at)}</td>
                  <td className="td">
                    <div className="messageCount">{callMessageCount(c)}</div>
                    <div className="small">messages</div>
                  </td>
                  <td className="td">
                    <div className={`recordingAvailability ${c.has_recording ? "recordingAvailable" : ""}`}>
                      <span className="recordingDot" aria-hidden="true" />
                      {c.has_recording ? "Audio available" : "Not recorded"}
                    </div>
                  </td>
                  <td className="td tRight">
                    <button
                      className="btn btnGhost viewCallButton"
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedCall(c);
                      }}
                    >
                      View conversation
                    </button>
                  </td>
                </tr>
              ))}
              {filteredCalls.length === 0 && (
                <tr>
                  <td className="td callRecordsEmpty" colSpan="6">
                    No call records match your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedCall && (
        <CallTranscriptModal
          call={selectedCall}
          onClose={() => setSelectedCall(null)}
        />
      )}
    </div>
  );
}

function getConversationMessages(call) {
  const messages = [];
  for (const turn of call.turns || []) {
    if (turn.transcript) {
      messages.push({
        id: `${turn.created_at}-user-${messages.length}`,
        role: "user",
        content: turn.transcript,
        createdAt: turn.created_at,
      });
    }
    if (turn.assistant_text) {
      messages.push({
        id: `${turn.created_at}-agent-${messages.length}`,
        role: "agent",
        content: turn.assistant_text,
        createdAt: turn.created_at,
      });
    }
  }

  if (messages.length === 0) {
    if (call.transcript) {
      messages.push({
        id: "legacy-user",
        role: "user",
        content: call.transcript,
        createdAt: call.created_at,
      });
    }
    if (call.assistant_text) {
      messages.push({
        id: "legacy-agent",
        role: "agent",
        content: call.assistant_text,
        createdAt: call.created_at,
      });
    }
  }
  return messages;
}

function formatMessageTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatAudioTime(value) {
  if (!Number.isFinite(value) || value < 0) return "0:00";
  const totalSeconds = Math.floor(value);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function CallRecordingPlayer({ src, recordedDuration }) {
  const audioRef = useRef(null);
  const animationFrameRef = useRef(null);
  const [duration, setDuration] = useState(
    Number.isFinite(Number(recordedDuration)) ? Number(recordedDuration) : 0,
  );
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;

    const syncDuration = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        setDuration(audio.duration);
        setLoading(false);
      }
    };
    const handleLoaded = () => {
      syncDuration();
      if (Number.isFinite(Number(recordedDuration)) && Number(recordedDuration) > 0) {
        setDuration((value) => value || Number(recordedDuration));
        setLoading(false);
      } else if (!Number.isFinite(audio.duration)) {
        // MediaRecorder WebM files can omit duration metadata. Seeking to the end
        // makes Chromium calculate it from the complete, range-enabled resource.
        audio.currentTime = Number.MAX_SAFE_INTEGER;
        audio.addEventListener(
          "timeupdate",
          () => {
            syncDuration();
            audio.currentTime = 0;
          },
          { once: true },
        );
      }
    };
    const handleCanPlay = () => setLoading(false);
    const handleEnded = () => {
      setPlaying(false);
      setCurrentTime(
        Number.isFinite(audio.duration)
          ? audio.duration
          : Number(recordedDuration) || 0,
      );
    };
    const handleError = () => {
      setLoading(false);
      setPlaying(false);
      setError("The call recording could not be loaded.");
    };

    audio.addEventListener("loadedmetadata", handleLoaded);
    audio.addEventListener("durationchange", syncDuration);
    audio.addEventListener("canplay", handleCanPlay);
    audio.addEventListener("ended", handleEnded);
    audio.addEventListener("error", handleError);
    audio.load();

    return () => {
      window.cancelAnimationFrame(animationFrameRef.current);
      audio.pause();
      audio.removeEventListener("loadedmetadata", handleLoaded);
      audio.removeEventListener("durationchange", syncDuration);
      audio.removeEventListener("canplay", handleCanPlay);
      audio.removeEventListener("ended", handleEnded);
      audio.removeEventListener("error", handleError);
    };
  }, [src, recordedDuration]);

  useEffect(() => {
    if (!playing) {
      window.cancelAnimationFrame(animationFrameRef.current);
      return undefined;
    }
    const updateProgress = () => {
      const audio = audioRef.current;
      if (audio) setCurrentTime(audio.currentTime);
      animationFrameRef.current = window.requestAnimationFrame(updateProgress);
    };
    animationFrameRef.current = window.requestAnimationFrame(updateProgress);
    return () => window.cancelAnimationFrame(animationFrameRef.current);
  }, [playing]);

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!audio || error) return;
    if (audio.paused) {
      if (duration && audio.currentTime >= duration - 0.05) audio.currentTime = 0;
      try {
        await audio.play();
        setPlaying(true);
      } catch {
        setError("Playback could not be started.");
      }
    } else {
      audio.pause();
      setPlaying(false);
      setCurrentTime(audio.currentTime);
    }
  }

  function seekTo(event) {
    const audio = audioRef.current;
    const nextTime = Number(event.target.value);
    if (!audio || !Number.isFinite(nextTime)) return;
    audio.currentTime = nextTime;
    setCurrentTime(nextTime);
  }

  function restart() {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    setCurrentTime(0);
  }

  function toggleMuted() {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = !audio.muted;
    setMuted(audio.muted);
  }

  const safeDuration = Number.isFinite(duration) && duration > 0 ? duration : 0;
  const progress = safeDuration ? Math.min((currentTime / safeDuration) * 100, 100) : 0;

  return (
    <div className="callRecordingPlayer">
      <audio ref={audioRef} preload="metadata" src={src} />
      <button
        className="recordingControl recordingPlay"
        type="button"
        onClick={togglePlayback}
        disabled={Boolean(error)}
        aria-label={playing ? "Pause recording" : "Play recording"}
      >
        {playing ? (
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h4v14H7zm6 0h4v14h-4z" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z" /></svg>
        )}
      </button>
      <button
        className="recordingControl recordingRestart"
        type="button"
        onClick={restart}
        disabled={Boolean(error)}
        aria-label="Restart recording"
        title="Restart"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 5a7 7 0 1 1-6.2 3.75L3 11V4h7L7.35 6.15A9 9 0 1 0 12 3z" />
        </svg>
      </button>
      <div className="recordingTimeline">
        <input
          className="recordingSeek"
          type="range"
          min="0"
          max={safeDuration || 0}
          step="0.01"
          value={Math.min(currentTime, safeDuration || 0)}
          onChange={seekTo}
          disabled={!safeDuration || Boolean(error)}
          aria-label="Recording position"
          style={{ "--recording-progress": `${progress}%` }}
        />
        <div className="recordingTimes" aria-live="off">
          <span>{formatAudioTime(currentTime)}</span>
          <span>{loading && !safeDuration ? "Loading…" : formatAudioTime(safeDuration)}</span>
        </div>
      </div>
      <button
        className="recordingControl"
        type="button"
        onClick={toggleMuted}
        disabled={Boolean(error)}
        aria-label={muted ? "Unmute recording" : "Mute recording"}
      >
        {muted ? (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 9v6h4l5 4V5L8 9zm11.5 1.1 1.4-1.4 2.1 2.1 2.1-2.1 1.4 1.4-2.1 2.1 2.1 2.1-1.4 1.4-2.1-2.1-2.1 2.1-1.4-1.4 2.1-2.1z" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 9v6h4l5 4V5L8 9zm11 3a3 3 0 0 0-1.5-2.6v5.2A3 3 0 0 0 15 12zm-1.5-7.1v2.05a5 5 0 0 1 0 10.1v2.05a7 7 0 0 0 0-14.2z" />
          </svg>
        )}
      </button>
      {error && <div className="recordingError" role="alert">{error}</div>}
    </div>
  );
}

function CallTranscriptModal({ call, onClose }) {
  const messages = getConversationMessages(call);

  return (
    <div className="modalBackdrop" onMouseDown={onClose}>
      <section
        className="modalCard modalWide callTranscriptModal"
        role="dialog"
        aria-modal="true"
        aria-label={`Call transcript ${call.id}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="callTranscriptHead">
          <div>
            <div className="h2">Call Conversation</div>
            <div className="small">
              {formatDateTime(call.created_at)} <span aria-hidden="true">&bull;</span>{" "}
              {call.patient_name || "Unknown Caller"}
            </div>
          </div>
          <button className="btn" type="button" onClick={onClose}>Close</button>
        </div>

        <div className="recordingPanel">
          <div>
            <div className="cardTitle">Full Call Recording</div>
            <div className="small">
              {call.has_recording
                ? "Patient and agent audio from this conversation."
                : "No recording is available for this call."}
            </div>
          </div>
          {call.has_recording && (
            <CallRecordingPlayer
              src={api.getCallRecordingUrl(call.session_id)}
              recordedDuration={call.recording_duration_seconds}
            />
          )}
        </div>

        <div className="cardTitle">Complete Conversation History</div>
        <div className="voiceHistory callTranscriptChat" role="log">
          {messages.length === 0 && (
            <div className="chatEmpty">
              <div className="chatEmptyTitle">No transcript is available</div>
            </div>
          )}
          {messages.map((message) => (
            <div
              key={message.id}
              className={`chatMessageRow ${message.role === "user" ? "chatMessageUser" : "chatMessageAgent"}`}
            >
              <div className="chatMessageGroup">
                <div className="chatMessageMeta">
                  <span>{message.role === "user" ? "Patient" : "AI Agent"}</span>
                  {message.createdAt && <span aria-hidden="true">&bull;</span>}
                  <time>{formatMessageTime(message.createdAt)}</time>
                </div>
                <div className="chatBubble urduText" dir="auto">{message.content}</div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
