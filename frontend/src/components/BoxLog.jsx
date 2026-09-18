import { WEIGHT_TOLERANCE_G } from "../constants/config";

export default function BoxLog({
  boxNumber,
  boxSize,
  voiceItems,
  itemsEditable,
  editingIndex,
  editingValue,
  setEditingValue,
  onAdjustQty,
  onStartEditing,
  onCommitEditing,
  onCancelEditing,
  onRemoveItem,
  voiceTotalWeight,
  weightDelta,
  weightInTolerance,
  phase,
  mismatchActive,
  boxLocked,
  voicePieces,
  flash,
}) {
  const cardFlashClass =
    phase === "saved" && flash
      ? "ring-2 ring-green-500 shadow-[0_0_24px_rgba(34,197,94,0.35)]"
      : "";

  return (
    <div className={`w-full rounded-xl transition-shadow ${cardFlashClass}`}>
      <div className="rounded-xl border border-slate-700 bg-slate-800 p-5 flex flex-col items-center text-center">
        <div className="flex items-center justify-center gap-2 mb-1">
          <span className="text-lg">📦</span>
          <h2 className="text-xl font-semibold">
            Box log (#{String(boxNumber).padStart(4, "0")})
          </h2>
        </div>
        <p className="text-xs text-slate-400 mb-4">
          Target {boxSize}pc ·{" "}
          {new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>

        <ul className="w-full divide-y divide-slate-700">
          {voiceItems.length === 0 && (
            <li className="py-6 text-center text-sm text-slate-400 italic">
              No items logged yet
            </li>
          )}
          {voiceItems.map((item, idx) => (
            <li
              key={item.name}
              className="flex items-center justify-center gap-2 py-2.5"
            >
              <button
                onClick={() => onAdjustQty(idx, -1)}
                disabled={!itemsEditable}
                aria-label={`Decrease ${item.name} quantity`}
                className="h-11 w-11 shrink-0 flex items-center justify-center rounded-lg border border-slate-600 text-slate-300 text-xl font-bold hover:bg-slate-700 active:bg-slate-600 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                −
              </button>

              {editingIndex === idx ? (
                <input
                  type="number"
                  inputMode="numeric"
                  min="0"
                  autoFocus
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  onBlur={onCommitEditing}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onCommitEditing();
                    if (e.key === "Escape") onCancelEditing();
                  }}
                  className="w-14 text-center text-sm font-semibold bg-slate-900 text-slate-50 rounded px-1.5 py-1 border border-green-500 focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              ) : (
                <button
                  onClick={() => onStartEditing(idx, item.qty)}
                  disabled={!itemsEditable}
                  aria-label={`Edit ${item.name} quantity`}
                  className="min-w-[44px] text-xs font-medium bg-slate-700 text-slate-50 rounded px-2 py-1.5 disabled:cursor-default enabled:hover:bg-slate-600 enabled:cursor-pointer"
                >
                  x{item.qty}
                </button>
              )}

              <button
                onClick={() => onAdjustQty(idx, 1)}
                disabled={!itemsEditable}
                aria-label={`Increase ${item.name} quantity`}
                className="h-11 w-11 shrink-0 flex items-center justify-center rounded-lg border border-slate-600 text-slate-300 text-xl font-bold hover:bg-slate-700 active:bg-slate-600 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                +
              </button>

              <span className="text-base">{item.name}</span>
              <span className="text-sm text-slate-400 font-mono">
                {(item.qty * item.unitWeight).toFixed(1)}g
              </span>

              <button
                onClick={() => onRemoveItem(idx)}
                disabled={!itemsEditable}
                aria-label={`Remove ${item.name} from box`}
                className="h-9 w-9 shrink-0 flex items-center justify-center rounded-lg border border-red-700/60 text-red-400 text-base font-bold hover:bg-red-500/10 active:bg-red-500/20 disabled:opacity-20 disabled:cursor-not-allowed"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>

        {voiceItems.length > 0 && (
          <div className="w-full mt-3 pt-3 border-t border-slate-700 flex flex-col items-center gap-1">
            <span className="text-sm font-mono text-slate-300">
              Itemized total: {voiceTotalWeight.toFixed(1)}g
            </span>
            {weightDelta !== null && (
              <span
                className={`text-xs font-medium ${
                  weightInTolerance ? "text-slate-500" : "text-yellow-400"
                }`}
              >
                {weightInTolerance
                  ? `Matches scale within ${WEIGHT_TOLERANCE_G.toFixed(1)}g`
                  : `Δ ${weightDelta > 0 ? "+" : ""}${weightDelta.toFixed(1)}g vs scale reading`}
              </span>
            )}
          </div>
        )}

        <div className="mt-3 flex items-center justify-center gap-4 text-base">
          <span>
            Total: {voicePieces}/{boxSize} pcs
          </span>
          {phase === "saved" ? (
            <span className="text-green-500 font-semibold">Verified ✅</span>
          ) : mismatchActive ? (
            boxLocked ? (
              <span className="text-red-500 font-semibold">
                Mismatch logged ⚠️
              </span>
            ) : (
              <span className="text-yellow-400 font-semibold">
                Needs fix ✏️
              </span>
            )
          ) : (
            <span className="text-slate-400">Pending…</span>
          )}
        </div>
      </div>
    </div>
  );
}
