export const PIECE_WEIGHT = 15; // g, fallback used to derive scale piece count
export const BOX_SIZE_OPTIONS = [6, 10, 16, 30, 50];
export const STARTING_BOX_NUMBER = 812; // first box number of the shift; increments from here
export const WEIGHT_TOLERANCE_G = 1.0; // small drift between nominal catalog weight and measured scale weight is expected

// Base URL for the Flask backend. Empty string in local dev (falls back to
// Vite's dev-server proxy / same-origin requests, i.e. today's behavior is
// unchanged); set VITE_API_URL in .env to point at a deployed backend, e.g.
// an ngrok tunnel, instead. Trailing slash stripped so callers can safely
// do `${API_BASE_URL}/api/...` without risking a double slash.
export const API_BASE_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export const ASSEMBLYAI_WS_ENDPOINT = "wss://streaming.assemblyai.com/v3/ws";
export const AUDIO_SAMPLE_RATE = 16000;
export const TOKEN_ENDPOINT = `${API_BASE_URL}/api/assemblyai-token`;