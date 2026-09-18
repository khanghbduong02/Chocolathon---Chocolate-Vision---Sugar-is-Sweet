export function normalizeItemMap(items = []) {
  const bySlug = new Map();

  for (const item of items || []) {
    const rawSlug = String(item?.slug || item?.name || '').trim();
    const slug = rawSlug
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[']/g, "")
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '');

    if (!slug) continue;

    const quantity = Number(item?.quantity ?? item?.qty ?? 1);
    const nextQty = Number.isFinite(quantity) && quantity > 0 ? quantity : 1;
    const existing = bySlug.get(slug);

    if (existing) {
      existing.quantity += nextQty;
      existing.name = existing.name || item?.name || slug;
      continue;
    }

    bySlug.set(slug, {
      slug,
      name: item?.name || slug,
      quantity: nextQty,
    });
  }

  return Object.fromEntries([...bySlug.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

export function compareVoiceAndCamera(voiceItems = [], cameraItems = []) {
  const voiceMap = normalizeItemMap(voiceItems);
  const cameraMap = normalizeItemMap(cameraItems);
  const slugs = new Set([...Object.keys(voiceMap), ...Object.keys(cameraMap)]);

  const byFlavor = [...slugs].sort().map((slug) => {
    const voiceQty = voiceMap[slug]?.quantity || 0;
    const cameraQty = cameraMap[slug]?.quantity || 0;

    let status = 'exact_match';
    if (voiceQty === 0 && cameraQty > 0) status = 'camera_only';
    else if (voiceQty > 0 && cameraQty === 0) status = 'voice_only';
    else if (voiceQty !== cameraQty) status = 'quantity_mismatch';

    return {
      slug,
      name: voiceMap[slug]?.name || cameraMap[slug]?.name || slug,
      status,
      voiceQty,
      cameraQty,
    };
  });

  const match = byFlavor.every((entry) => entry.status === 'exact_match');

  return {
    match,
    overall: match ? 'match' : 'mismatch',
    byFlavor,
    totals: {
      voice: Object.values(voiceMap).reduce((sum, item) => sum + item.quantity, 0),
      camera: Object.values(cameraMap).reduce((sum, item) => sum + item.quantity, 0),
    },
  };
}
