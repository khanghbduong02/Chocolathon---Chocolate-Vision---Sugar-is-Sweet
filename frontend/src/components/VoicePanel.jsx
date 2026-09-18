import { getPanelHalfClass, panelStatusNote, panelStatusTextClass } from "../utils/statusStyles";

export default function VoicePanel({
  phase,
  boxLocked,
  voiceItems,
  liveTranscript,
  voicePieces,
  voiceStatus,
  boxSize,
}) {
  const showNote = phase !== "saved" && phase !== "mismatch" && panelStatusNote[voiceStatus];

  return (
    <div
      className={`p-6 flex flex-col items-center text-center transition-colors ${getPanelHalfClass(
        phase,
        boxLocked,
        voiceStatus
      )}`}
    >
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🎙️</span>
        <h2 className="text-2xl font-semibold">Spoken flavors</h2>
      </div>

      {voiceItems.length === 0 && !liveTranscript && (
        <p className="panel-empty-copy text-lg italic">
          {phase === "idle" ? "Awaiting audio input" : "Listening for spoken flavors…"}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-center gap-3">
        {voiceItems.map((item, idx) => (
          <span
            key={idx}
            className="voice-item-chip inline-flex items-center rounded-full font-medium text-base px-4 py-2"
          >
            {item.quantity > 1 ? `x${item.quantity} ` : ""}
            {item.name}
          </span>
        ))}
      </div>

      {liveTranscript && (
        <p className="live-transcript mt-3 italic text-lg">"{liveTranscript}"</p>
      )}

      {voiceItems.length > 0 && (
        <span className="panel-muted-total mt-3 text-xl">{voicePieces} pieces spoken</span>
      )}
      {showNote && (
        <span className={`mt-1 text-sm font-medium ${panelStatusTextClass(voiceStatus)}`}>
          {panelStatusNote[voiceStatus](boxSize, voicePieces)}
        </span>
      )}
    </div>
  );
}