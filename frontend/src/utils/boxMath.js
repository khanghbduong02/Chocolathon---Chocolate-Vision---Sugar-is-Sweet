// Pure math helpers for box packing — no React, no side effects.
// Kept separate so they're trivially unit-testable on their own.

export function totalPieces(items) {
  return items.reduce((sum, i) => sum + i.qty, 0);
}

export function totalWeight(items) {
  return items.reduce((sum, i) => sum + i.qty * i.unitWeight, 0);
}

// Compares a live count against the box target so each panel can show its
// own under/at/over cue before the box is committed.
export function pieceStatus(pieces, target) {
  if (pieces === 0) return "none";
  if (pieces < target) return "under";
  if (pieces === target) return "match";
  return "over";
}