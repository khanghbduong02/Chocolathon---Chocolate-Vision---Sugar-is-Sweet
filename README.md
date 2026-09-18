# Chocolate Vision + Cocoa Vision

A merged cashier workflow that combines a webcam-based YOLO inspection flow with live AssemblyAI voice transcription. The app captures a packed chocolate box, listens to the cashier speak flavors as they work, compares the spoken list against the CV prediction, and saves a single auditable order record with the original and annotated photos.

## Architecture

- Flask API at the repo root serves both the YOLO `/api/scan` route and the voice token route.
- React + Vite frontend in `frontend/` provides the live camera preview, voice panel, review, and save flow.
- `pipeline/` holds the flavor catalog and YOLO training/inference helpers used by the Python detection stack.
- `labels.json` is the shared source of truth for flavor names and aliases used by camera detection and transcript matching.

## Environment and config

Required environment variables in a shell or `.env` file:

- `SPEECH_TO_TEXT_API_KEY` — AssemblyAI API key used by the server-side token endpoint
- `FLASK_ENV` — optional, for local debugging

Model weights should be placed under `runs/detect/.../weights/best.pt` or passed via `--weights` when starting the Python API. If no custom checkpoint is found, the bundled `yolov8n.pt` fallback loads so the service can start; custom weights are required for chocolate-flavor detection quality.

## Local setup

```bash
cd d:\Chocolathon\Chocoa-Vision
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd frontend
npm install
```

## Run the app

### API

```bash
cd d:\Chocolathon\Chocoa-Vision
.venv\Scripts\activate
python app.py --host 127.0.0.1 --port 5000
```

### Frontend

```bash
cd d:\Chocolathon\Chocoa-Vision\frontend
npm run dev
```

Open the frontend URL printed by Vite and allow microphone access when prompted.

## Merged workflow

1. Choose a box size.
2. Press Start New Box to begin a new recording and start the mic stream.
3. Pack the box while speaking flavors aloud.
4. Finish recording and scan the current camera frame. The app sends the native-resolution image to `/api/scan` and compares the voice list with the camera prediction.
5. Review per-flavor status, camera-only detections, and quantities inline. Edit only the final voice list, then save the confirmed order through `/api/orders`.
6. Reopen the saved original or annotated photo from the order log for verification.

## Storage schema

The order CSV remains backward compatible with the Chocolate Vision format and adds optional fields when the app is used in the merged flow. Each row can retain:

- `id`
- `timestamp`
- `total_pieces`
- `items`
- `photo_id`
- `box_size`
- `transcript_items` — the voice-derived list
- `camera_items` — the read-only YOLO prediction
- `comparison_status` — `match` or `mismatch`
- `pack_time_seconds`

Captured images are stored under:

- `orders/captures/<photo_id>_capture.jpg`
- `orders/captures/<photo_id>_annotated.jpg`

## Known requirements and limitations

- Requires a browser that supports microphone capture and webcam access.
- AssemblyAI token minting needs a valid API key and internet access.
- The fallback YOLO model can start the service but is not trained for the chocolate catalog; use a trained checkpoint for meaningful scan results.
- Camera and transcript matching are best-effort; cashier review is still required before committing a final order.

## Development checks

```bash
cd d:\Chocolathon\Chocoa-Vision\frontend
npm run test
npm run lint
npm run build

cd d:\Chocolathon\Chocoa-Vision
python -m py_compile app.py backend/app.py pipeline/*.py
```

## Notes

This repo intentionally keeps the Chocolate Vision Python backend and the Cocoa Vision voice UI while combining them into one merged checkout flow for real-world packing verification.
