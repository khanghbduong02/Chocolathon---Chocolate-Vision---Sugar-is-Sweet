export function topFlavors(orderLog, limit = 5) {
  const counts = new Map();
  for (const box of orderLog) {
    const items = box.chocolates || box.items || [];
    for (const item of items) {
      const flavor = item.flavor || item.name;
      counts.set(flavor, (counts.get(flavor) || 0) + Number(item.quantity || 0));
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([flavor, qty]) => ({ flavor, qty }));
}

// All k-element subsets of arr (arr assumed already sorted/unique).
function combinations(arr, k) {
  const results = [];
  function backtrack(start, combo) {
    if (combo.length === k) {
      results.push([...combo]);
      return;
    }
    for (let i = start; i < arr.length; i++) {
      combo.push(arr[i]);
      backtrack(i + 1, combo);
      combo.pop();
    }
  }
  backtrack(0, []);
  return results;
}

// Finds flavor combinations that recur across multiple boxes, using subset
// matching: a box contributes to every minSize..maxSize-sized subset of its
// distinct flavors, not just its full flavor set. So a pairing shows up
// even when it's part of a bigger, otherwise-different box each time.
// There's no customer identity in the log, so this surfaces "sets that keep
// getting packed together" rather than true repeat-customer behavior.
export function topCombinations(
  orderLog,
  { minBoxes = 2, limit = 5, minSize = 2, maxSize = 2 } = {},
) {
  const comboCounts = new Map();
  for (const box of orderLog) {
    const items = box.chocolates || box.items || [];
    const flavors = [...new Set(items.map((item) => item.flavor || item.name).filter(Boolean))].sort();
    const hi = Math.min(maxSize, flavors.length);
    for (let k = minSize; k <= hi; k++) {
      for (const subset of combinations(flavors, k)) {
        const key = subset.join(" + ");
        comboCounts.set(key, (comboCounts.get(key) || 0) + 1);
      }
    }
  }
  return [...comboCounts.entries()]
    .filter(([, count]) => count >= minBoxes)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([combo, count]) => ({ combo, count }));
}