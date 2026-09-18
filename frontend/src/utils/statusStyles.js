// Pure helpers for the phase status banner — no React, just derived display state.

export function getBannerCopy(phase, { remaining, elapsed }) {
  const copy = {
    idle: "Click 'Start New Box' to begin.",
    listening: 'Listening… Click "Finish recording and scan box" when done.',
    scanning: "Scanning box… Please wait.",
    review: "Review results, edit if needed, then save.",
    buffering: `Waiting for ${remaining} more item${remaining === 1 ? "" : "s"}…`,
    saved: `Box saved in ${elapsed.toFixed(2)}s`,
  };
  return copy[phase];
}

export function getBannerIcon(phase) {
  return {
    idle: "🛎️",
    listening: "🎙️",
    scanning: "🔎",
    review: "🧾",
    buffering: "⏳",
    saved: "✅",
  }[phase];
}

// A quiet status badge, not a button: thin border, tinted (never solid)
// background, medium weight text — deliberately understated next to the
// bold green CTA below so it can't be mistaken for something tappable.
export function getBannerClass(phase) {
  return {
    idle: "status-banner status-idle",
    listening: "status-banner status-warn",
    scanning: "status-banner status-warn",
    review: "status-banner status-idle",
    buffering: "status-banner status-warn",
    saved: "status-banner status-good",
  }[phase];
}

// Border/background for each half of the packing panel. Before a box is
// committed, each half is judged independently against the box target so
// a cashier sees an early under/over cue, not just a final pass/fail.
export function getPanelHalfClass(phase, boxLocked, status) {
  if (phase === "saved") return "panel-good";
  if (status === "match") return "panel-good";
  if (status === "under") return "panel-warn";
  if (status === "over") return "panel-bad";
  return "panel-neutral";
}

export const panelStatusNote = {
  none: null,
  under: (target, count) => `${target - count} short of ${target}`,
  match: () => "On target",
  over: (target, count) => `${count - target} over ${target}`,
};

export function panelStatusTextClass(status) {
  if (status === "match") return "status-text-good";
  if (status === "over") return "status-text-bad";
  return "status-text-warn";
}