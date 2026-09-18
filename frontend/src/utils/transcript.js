import { FLAVOR_CATALOG } from "../constants/flavorCatalog.js";

const NUMBER_WORDS = {
  one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9,
};

const DELETE_KEYWORDS = [
  "remove",
  "delete",
  "no more",
  "don't want",
  "take out",
  "cancel",
];

function detectAction(precedingText) {
  const sorted = [...DELETE_KEYWORDS].sort((a, b) => b.length - a.length);
  for (const kw of sorted) {
    if (precedingText.includes(kw)) return "remove";
  }
  return "set";
}

export function parseTranscript(transcript, catalog = FLAVOR_CATALOG) {
  const lower = ` ${transcript.toLowerCase()} `;
  const found = [];

  catalog.forEach((flavor) => {
    const needle = flavor.name.toLowerCase();
    let idx = lower.indexOf(needle);
    let matched = false;
    let qty = null;
    let action = "set";

    while (idx !== -1) {
      matched = true;

      const precedingText = lower.slice(Math.max(0, idx - 25), idx).trim();
      const words = precedingText.split(/\s+/);
      const lastWord = words[words.length - 1];

      let thisQty = null;
      if (/^\d+$/.test(lastWord)) thisQty = parseInt(lastWord, 10);
      else if (NUMBER_WORDS[lastWord]) thisQty = NUMBER_WORDS[lastWord];

      if (thisQty !== null) qty = thisQty;

      action = detectAction(precedingText);

      idx = lower.indexOf(needle, idx + needle.length);
    }

    if (matched) {
      found.push({ name: flavor.name, qty, unitWeight: flavor.unitWeight, action });
    }
  });

  return found;
}