import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { compareVoiceAndCamera } from "../utils/compareVoiceAndCamera";
import { API_BASE_URL, STARTING_BOX_NUMBER, apiFetch } from "../constants/config";

const initialState = {
  phase: "idle",
  voiceItems: [],
  cameraItems: [],
  comparison: null,
  photoId: "",
  annotatedImage: "",
  capturedImage: "",
  orderLog: [],
  boxNumber: STARTING_BOX_NUMBER,
  boxLocked: false,
};

function reducer(state, action) {
  switch (action.type) {
    case "HYDRATE": return { ...state, orderLog: action.orders, boxNumber: action.orders.reduce((max, order) => Math.max(max, Number(order.id) || 0), STARTING_BOX_NUMBER - 1) + 1 };
    case "BEGIN": return { ...initialState, orderLog: state.orderLog, boxNumber: state.boxNumber, phase: "listening" };
    case "RESET": return { ...initialState, orderLog: state.orderLog, boxNumber: state.boxNumber };
    case "VOICE": return { ...state, voiceItems: action.items };
    case "SCAN_RESULT": return { ...state, phase: "review", cameraItems: action.cameraItems, comparison: action.comparison, photoId: action.photoId, annotatedImage: action.annotatedImage, capturedImage: action.capturedImage };
    case "SET_PHASE": return { ...state, phase: action.phase };
    case "COMMIT": return { ...state, phase: "saved", orderLog: [action.order, ...state.orderLog], boxNumber: state.boxNumber + 1, boxLocked: true };
    case "UPDATE_ORDER": return { ...state, orderLog: state.orderLog.map((order) => String(order.id) === String(action.order.id) ? action.order : order) };
    case "DELETE_ORDER": return { ...state, orderLog: state.orderLog.filter((order) => String(order.id) !== String(action.orderId)) };
    case "CLEAR": return { ...state, orderLog: [], boxNumber: STARTING_BOX_NUMBER };
    default: return state;
  }
}

function normalizeVoiceItem(item) {
  const name = String(item.name || "").trim();
  const slug = name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[']/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
  return { slug: item.slug || slug, name, quantity: Number(item.quantity ?? item.qty ?? 1) };
}

export function useBoxPacking({ startMic, stopMic, setLiveTranscript, boxSize }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [elapsed, setElapsed] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const timerRef = useRef(null);
  const startTimeRef = useRef(0);

  useEffect(() => {
    let active = true;
    apiFetch(`${API_BASE_URL}/api/orders`).then((response) => response.ok ? response.json() : Promise.reject(new Error("Could not load orders."))).then((data) => { if (active) dispatch({ type: "HYDRATE", orders: data.orders || [] }); }).catch(() => {});
    return () => { active = false; };
  }, []);

  const clearTimer = useCallback(() => { if (timerRef.current) clearInterval(timerRef.current); timerRef.current = null; }, []);

  const setVoiceItems = useCallback((updater) => {
    dispatch({ type: "VOICE", items: typeof updater === "function" ? updater(state.voiceItems) : updater });
  }, [state.voiceItems]);

  const addVoiceMatches = useCallback((matches) => {
    // Ignore late transcripts that arrive after reset/stop.
    if (state.phase !== "listening") return;
    dispatch({ type: "VOICE", items: matches.reduce((items, match) => {
      const item = normalizeVoiceItem(match);
      const index = items.findIndex((candidate) => candidate.slug === item.slug || candidate.name === item.name);
      if (match.action === "remove") return items.filter((_, itemIndex) => itemIndex !== index);
      if (index >= 0) items[index] = { ...items[index], quantity: item.quantity };
      else items.push(item);
      return items;
    }, [...state.voiceItems]) });
  }, [state.voiceItems, state.phase]);

  function beginBox() {
    stopMic();
    clearTimer();
    setElapsed(0);
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => setElapsed((Date.now() - startTimeRef.current) / 1000), 100);
    dispatch({ type: "BEGIN" });
    startMic();
  }

  function resetToIdle() {
    clearTimer();
    setElapsed(0);
    stopMic();
    setLiveTranscript("");
    setSaveError("");
    dispatch({ type: "RESET" });
  }

  async function finishRecordingAndScan(capture) {
    if (state.phase !== "listening") return;
    setSaveError("");
    dispatch({ type: "SET_PHASE", phase: "scanning" });
    clearTimer();
    stopMic();
    try {
      const blob = await capture();
      const capturedImage = URL.createObjectURL(blob);
      const form = new FormData();
      form.append("image", blob, "box.jpg");
      // No Content-Type here: the browser sets the multipart boundary itself.
      const response = await apiFetch(`${API_BASE_URL}/api/scan`, { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Camera scan failed.");
      const cameraItems = (data.items || []).map((item) => ({ slug: item.slug, name: item.name, quantity: item.quantity }));
      dispatch({ type: "SCAN_RESULT", cameraItems, comparison: compareVoiceAndCamera(state.voiceItems, cameraItems), photoId: data.photo_id, annotatedImage: data.annotated_image, capturedImage });
    } catch (error) {
      setSaveError(error.message || "Could not scan the box.");
      dispatch({ type: "SET_PHASE", phase: "listening" });
    }
  }

  function adjustItemQty(index, delta) {
    if (state.phase !== "review") return;
    dispatch({ type: "VOICE", items: state.voiceItems.map((item, itemIndex) => itemIndex === index ? { ...item, quantity: Math.max(0, item.quantity + delta) } : item).filter((item) => item.quantity > 0) });
  }

  function removeItem(index) { dispatch({ type: "VOICE", items: state.voiceItems.filter((_, itemIndex) => itemIndex !== index) }); }

  const comparison = state.cameraItems.length > 0
    ? compareVoiceAndCamera(state.voiceItems, state.cameraItems)
    : state.comparison;

  async function saveOrder() {
    if (!comparison || saving) return;
    setSaving(true);
    setSaveError("");
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/orders`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        items: state.voiceItems,
        transcript_items: state.voiceItems,
        camera_items: state.cameraItems,
        comparison_status: comparison.overall,
        photo_id: state.photoId,
        box_size: boxSize,
        pack_time_seconds: Number(elapsed.toFixed(2)),
      }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not save order.");
      dispatch({ type: "COMMIT", order: data.order });
    } catch (error) { setSaveError(error.message || "Could not save order."); }
    finally { setSaving(false); }
  }

  async function updateOrder(orderId, items, boxSizeOverride, comparisonStatus) {
    const response = await apiFetch(`${API_BASE_URL}/api/orders/${orderId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, box_size: boxSizeOverride ?? null, comparison_status: comparisonStatus }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not update order.");
    dispatch({ type: "UPDATE_ORDER", order: data.order });
  }

  async function deleteOrder(orderId) {
    const response = await apiFetch(`${API_BASE_URL}/api/orders/${orderId}`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not delete order.");
    dispatch({ type: "DELETE_ORDER", orderId });
  }

  function downloadOrderLog() {
    const blob = new Blob([JSON.stringify(state.orderLog, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = "chocoa-vision-orders.json"; anchor.click(); URL.revokeObjectURL(url);
  }

  async function clearOrderLog() {
    const response = await apiFetch(`${API_BASE_URL}/api/orders`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not delete logs.");
    dispatch({ type: "CLEAR" });
  }

  return {
    ...state, elapsed, saving, saveError, voiceItems: state.voiceItems, itemsEditable: state.phase === "review" && !state.boxLocked,
    voicePieces: state.voiceItems.reduce((sum, item) => sum + item.quantity, 0),
    remaining: Math.max(boxSize - state.voiceItems.reduce((sum, item) => sum + item.quantity, 0), 0),
    beginBox, resetToIdle, finishRecordingAndScan, addVoiceMatches, setVoiceItems, adjustItemQty, removeItem, saveOrder, updateOrder, deleteOrder, downloadOrderLog, clearOrderLog,
    comparison,
  };
}