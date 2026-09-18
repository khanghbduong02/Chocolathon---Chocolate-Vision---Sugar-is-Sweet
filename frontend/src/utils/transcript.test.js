import test from "node:test";
import assert from "node:assert/strict";
import { parseTranscript } from "./transcript.js";

test("parses numeric quantities and delete commands from the shared catalog", () => {
  const catalog = [{ name: "Salted Caramel", unitWeight: 15 }];
  assert.deepEqual(parseTranscript("two salted caramel", catalog), [
    { name: "Salted Caramel", qty: 2, unitWeight: 15, action: "set" },
  ]);
  assert.deepEqual(parseTranscript("remove salted caramel", catalog), [
    { name: "Salted Caramel", qty: null, unitWeight: 15, action: "remove" },
  ]);
});
