import { useMemo } from "react";
import { topFlavors, topCombinations } from "../utils/orderAnalytics";

export default function InsightsPanel({ orderLog, onClose }) {
  const flavorStats = useMemo(() => topFlavors(orderLog, 5), [orderLog]);
  const comboStats = useMemo(() => topCombinations(orderLog, { limit: 5 }), [orderLog]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="insights-modal w-full max-w-md mt-16 rounded-xl p-5 flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">📊 Session insights</h2>
          <button
            onClick={onClose}
            className="modal-close"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div>
          <h3 className="insights-heading text-sm font-semibold mb-2">Most-picked pieces</h3>
          {flavorStats.length === 0 ? (
            <p className="insights-muted text-xs">Not enough data yet.</p>
          ) : (
            <ol className="space-y-1">
              {flavorStats.map(({ flavor, qty }, i) => (
                <li key={flavor} className="insights-row flex justify-between text-sm">
                  <span>{i + 1}. {flavor}</span>
                  <span className="insights-muted">{qty} pcs</span>
                </li>
              ))}
            </ol>
          )}
        </div>

        <div>
          <h3 className="insights-heading text-sm font-semibold mb-2">Popular combos</h3>
          {comboStats.length === 0 ? (
            <p className="insights-muted text-xs">
              No repeated flavor pairs yet — needs the same pair in 2+ boxes.
            </p>
          ) : (
            <ol className="space-y-1">
              {comboStats.map(({ combo, count }, i) => (
                <li key={combo} className="insights-row flex justify-between gap-3 text-sm">
                  <span>{i + 1}. {combo}</span>
                  <span className="insights-muted whitespace-nowrap">{count}x</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}