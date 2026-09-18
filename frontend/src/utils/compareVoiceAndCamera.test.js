import test from 'node:test';
import assert from 'node:assert/strict';

import { compareVoiceAndCamera, normalizeItemMap } from './compareVoiceAndCamera.js';

test('normalizeItemMap merges quantities and aliases', () => {
  const normalized = normalizeItemMap([
    { slug: 'caramel_apple_cider', name: 'Caramel Apple Cider', quantity: 2 },
    { slug: 'caramel-apple-cider', name: 'Caramel Apple Cider', quantity: 1 },
    { name: 'Salted Caramel', quantity: 1 },
  ]);

  assert.deepEqual(normalized, {
    caramel_apple_cider: { slug: 'caramel_apple_cider', name: 'Caramel Apple Cider', quantity: 3 },
    salted_caramel: { slug: 'salted_caramel', name: 'Salted Caramel', quantity: 1 },
  });
});

test('compareVoiceAndCamera reports exact matches and mismatches', () => {
  const result = compareVoiceAndCamera(
    [{ slug: 'caramel_apple_cider', name: 'Caramel Apple Cider', quantity: 2 }, { slug: 'banana', name: 'Banana', quantity: 1 }],
    [{ slug: 'caramel_apple_cider', name: 'Caramel Apple Cider', quantity: 1 }, { slug: 'banana', name: 'Banana', quantity: 1 }, { slug: 'espresso_martini', name: 'Espresso Martini', quantity: 2 }],
  );

  assert.equal(result.match, false);
  assert.equal(result.overall, 'mismatch');
  assert.deepEqual(result.byFlavor.map((entry) => ({ slug: entry.slug, status: entry.status, voiceQty: entry.voiceQty, cameraQty: entry.cameraQty })), [
    { slug: 'banana', status: 'exact_match', voiceQty: 1, cameraQty: 1 },
    { slug: 'caramel_apple_cider', status: 'quantity_mismatch', voiceQty: 2, cameraQty: 1 },
    { slug: 'espresso_martini', status: 'camera_only', voiceQty: 0, cameraQty: 2 },
  ]);
});

test('compareVoiceAndCamera handles voice-only addition', () => {
  const result = compareVoiceAndCamera(
    [{ slug: 'confetti_cake', name: 'Confetti Cake', quantity: 3 }],
    [],
  );

  assert.equal(result.match, false);
  assert.equal(result.overall, 'mismatch');
  assert.equal(result.byFlavor[0].status, 'voice_only');
});
