export default function BoxControls({ phase, boxLocked, onBeginBox, onReset, onFinish }) {
  const startDisabled =
    phase !== "idle" && phase !== "saved" && !(phase === "mismatch" && boxLocked);

  return (
    <div className="control-bar">
      <button
        onClick={onBeginBox}
        disabled={startDisabled}
        className="button primary control-button"
      >
        Start New Box
      </button>
      {phase === "listening" && <button onClick={onFinish} className="button gold control-button">Finish recording and scan box</button>}
      <button
        onClick={onReset}
        className="button secondary reset-button"
      >
        Reset
      </button>
    </div>
  );
}