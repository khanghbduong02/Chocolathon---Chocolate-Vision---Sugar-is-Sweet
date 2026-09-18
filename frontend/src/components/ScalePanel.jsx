import { getPanelHalfClass, panelStatusNote, panelStatusTextClass } from "../utils/statusStyles";

export default function ScalePanel({
  phase,
  boxLocked,
  scaleWeight,
  scalePieces,
  scaleStatus,
  boxSize,
  simulatedCorrectWeight,
  simulatedWrongWeight,
  onReportWeight,
}) {
  const showControls =
    phase === "listening" || phase === "buffering" || (phase === "mismatch" && !boxLocked);
  const showNote = phase !== "saved" && phase !== "mismatch" && panelStatusNote[scaleStatus];

  return (
    <div
      className={`p-6 flex flex-col items-center text-center border-b sm:border-b-0 sm:border-r border-slate-700 transition-colors ${getPanelHalfClass(
        phase,
        boxLocked,
        scaleStatus
      )}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="text-2xl">⚖️</span>
        <h2 className="text-2xl font-semibold">Scale readout</h2>
      </div>
      <span className="font-mono text-6xl font-bold tabular-nums">
        +{scaleWeight.toFixed(1)}g
      </span>
      <span className="mt-2 text-xl text-slate-400">{scalePieces || 0} pieces on scale</span>
      {showNote && (
        <span className={`mt-1 text-sm font-medium ${panelStatusTextClass(scaleStatus)}`}>
          {panelStatusNote[scaleStatus](boxSize, scalePieces)}
        </span>
      )}

      {showControls && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          <button
            onClick={() => onReportWeight(simulatedCorrectWeight)}
            className="min-h-[56px] px-6 rounded-lg border border-slate-600 text-slate-300 text-base font-medium hover:bg-slate-700"
          >
            Simulate correct weight ({simulatedCorrectWeight.toFixed(1)}g)
          </button>
          <button
            onClick={() => onReportWeight(simulatedWrongWeight)}
            className="min-h-[56px] px-6 rounded-lg border border-red-600 text-red-400 text-base font-medium hover:bg-red-500/10"
          >
            Simulate wrong weight ({simulatedWrongWeight.toFixed(1)}g)
          </button>
        </div>
      )}
    </div>
  );
}