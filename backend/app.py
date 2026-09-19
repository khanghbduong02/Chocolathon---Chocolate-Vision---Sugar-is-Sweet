"""
Checkout counter: photograph a packed box, get the flavor list, log the order.

USAGE
-----
    python backend/app.py
    python app.py
    python backend/app.py --weights runs/detect/chocolate_model-2/weights/best.pt

React UI (Vite + Tailwind) talks to this API. In two terminals:

    python backend/app.py
    cd frontend && npm install && npm run dev

Then open http://127.0.0.1:5173 — Capture snaps the webcam, or drop in a photo.
Detection is a draft: edit quantities, add or remove flavors, then Save to
orders.csv. Existing rows can be edited the same way.

After `npm run build` in frontend/, this process can also serve the UI at
http://127.0.0.1:5000.

CORS is locked to a single allowed origin (ALLOWED_ORIGIN below) rather than
"*" - the deployed frontend lives at a fixed Vercel URL, so there's no need
to accept requests from anywhere else.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib import request as urllib_request
from urllib.parse import urlencode

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
from ultralytics import YOLO

import sys

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "pipeline"))

from flavors import display_name, load_labels, slugify, unique_class_slugs
from paths import use_repo_root
from predict_box import draw_predictions
DIST_DIR = ROOT / "frontend" / "dist"
ORDERS_CSV = ROOT / "orders.csv"
CAPTURE_DIR = ROOT / "orders" / "captures"
CSV_HEADERS = [
    "id", "timestamp", "total_pieces", "items", "photo_id", "box_size",
    "transcript_items", "camera_items", "comparison_status", "pack_time_seconds",
]
WEIGHT_CANDIDATES = [
    ROOT / "runs/detect/chocolate_model-2/weights/best.pt",
    ROOT / "runs/detect/chocolate_model/weights/best.pt",
    ROOT / "runs/detect/chocolate_model_gridprep/weights/best.pt",
    ROOT / "yolov8n.pt",
    ROOT / "yolov8s.pt",
]

# Single allowed frontend origin. Override via the ALLOWED_ORIGIN env var
# (in backend/.env) if you ever need a different deployed URL without
# editing code - it's read once at import time, same as the weights list.
ALLOWED_ORIGIN = os.getenv(
    "ALLOWED_ORIGIN", "https://chocolathon-chocolate-vision-sugar.vercel.app"
).rstrip("/")

app = Flask(__name__, static_folder=None)
_csv_lock = threading.Lock()
_model = None
_conf = 0.25
_iou = 0.4


def default_weights() -> str:
    for path in WEIGHT_CANDIDATES:
        if path.exists():
            return str(path)
    return "yolov8s.pt"


def load_model(weights: Path):
    global _model
    print(f"Loading model from {weights}...")
    _model = YOLO(str(weights))


def decode_image(data: bytes):
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not read the uploaded image")
    return image


def encode_jpeg(image) -> str:
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise ValueError("Could not encode the annotated image")
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def photo_file(photo_id: str, kind: str) -> Path:
    return CAPTURE_DIR / f"{photo_id}_{kind}.jpg"


def valid_photo_id(photo_id: str) -> bool:
    return bool(photo_id) and re.fullmatch(r"[0-9_]+", photo_id) is not None


def photo_exists(photo_id: str) -> bool:
    return valid_photo_id(photo_id) and (
        photo_file(photo_id, "capture").is_file() or photo_file(photo_id, "annotated").is_file()
    )


def new_photo_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    while photo_file(stamp, "capture").exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return stamp


def attach_photo_id(payload_id) -> str:
    photo_id = str(payload_id or "").strip()
    if not photo_id:
        return ""
    if not photo_exists(photo_id):
        raise ValueError("Saved photo was not found")
    return photo_id


BOX_SIZES = (6, 10, 16, 30, 50)


def parse_box_size(value):
    if value in (None, ""):
        return None
    try:
        size = int(value)
    except (TypeError, ValueError):
        raise ValueError("Box size must be 6, 10, 16, 30, or 50")
    if size not in BOX_SIZES:
        raise ValueError("Box size must be 6, 10, 16, 30, or 50")
    return size


def format_items(counts: Counter) -> list[dict]:
    items = []
    for slug, quantity in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
        items.append({
            "slug": slug,
            "name": display_name(slug),
            "quantity": int(quantity),
        })
    return items


def items_csv_cell(items: list[dict]) -> str:
    return "; ".join(f"{item['name']} x{item['quantity']}" for item in items)


def parse_items_cell(cell: str) -> list[dict]:
    items = []
    for part in (cell or "").split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, qty = part.rpartition(" x")
        if not name:
            name, qty = part, "1"
        try:
            quantity = max(1, int(qty))
        except ValueError:
            name, quantity = part, 1
        items.append({"slug": slugify(name), "name": name.strip(), "quantity": quantity})
    return items


def parse_json_items(cell: str) -> list[dict]:
    if not cell:
        return []
    try:
        value = json.loads(cell)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def normalize_items(raw_items) -> list[dict]:
    if not isinstance(raw_items, list):
        raise ValueError("items must be a list")
    merged = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        slug = slugify(str(raw.get("slug") or raw.get("name") or ""))
        if not slug:
            continue
        try:
            quantity = int(raw.get("quantity", 0))
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        name = str(raw.get("name") or display_name(slug)).strip() or display_name(slug)
        if slug in merged:
            merged[slug]["quantity"] += quantity
        else:
            merged[slug] = {"slug": slug, "name": name, "quantity": quantity}
    items = sorted(merged.values(), key=lambda item: item["name"].lower())
    if not items:
        raise ValueError("Add at least one flavor")
    return items


def total_pieces(items: list[dict]) -> int:
    return sum(int(item["quantity"]) for item in items)


def flavor_catalog() -> list[dict]:
    labels = load_labels()
    catalog = {}
    for slug in unique_class_slugs(labels):
        catalog[slug] = {"slug": slug, "name": display_name(slug, labels)}
    if _model is not None:
        for name in _model.names.values():
            if name not in catalog:
                catalog[name] = {"slug": name, "name": display_name(name, labels)}
    return sorted(catalog.values(), key=lambda item: item["name"].lower())


def read_all_orders() -> list[dict]:
    if not ORDERS_CSV.exists():
        return []
    with ORDERS_CSV.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    orders = []
    for index, row in enumerate(rows, start=1):
        order_id = str(row.get("id") or "").strip() or str(index)
        items = parse_items_cell(row.get("items", ""))
        timestamp = row.get("timestamp") or ""
        try:
            total = int(row.get("total_pieces") or total_pieces(items) or 0)
        except ValueError:
            total = total_pieces(items)
        photo_id = str(row.get("photo_id") or "").strip()
        transcript_items = parse_json_items(row.get("transcript_items", "")) or items
        camera_items = parse_json_items(row.get("camera_items", "")) or items
        orders.append({
            "id": order_id,
            "timestamp": timestamp,
            "total_pieces": total,
            "items": items,
            "items_text": items_csv_cell(items) if items else row.get("items", ""),
            "photo_id": photo_id,
            "has_photo": photo_exists(photo_id),
            "box_size": int(row["box_size"]) if str(row.get("box_size") or "").isdigit() else None,
            "transcript_items": transcript_items,
            "camera_items": camera_items,
            "comparison_status": row.get("comparison_status") or None,
            "pack_time_seconds": float(row["pack_time_seconds"]) if row.get("pack_time_seconds") else None,
        })
    return orders


def write_all_orders(orders: list[dict]):
    ORDERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with ORDERS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADERS)
        for order in orders:
            items = order["items"] if isinstance(order.get("items"), list) else parse_items_cell(order.get("items_text", ""))
            writer.writerow([
                order["id"],
                order["timestamp"],
                total_pieces(items),
                items_csv_cell(items),
                order.get("photo_id") or "",
                order.get("box_size") or "",
                json.dumps(order.get("transcript_items") or [], separators=(",", ":")),
                json.dumps(order.get("camera_items") or [], separators=(",", ":")),
                order.get("comparison_status") or "",
                order.get("pack_time_seconds") if order.get("pack_time_seconds") is not None else "",
            ])


def next_order_id(orders: list[dict]) -> str:
    numbers = []
    for order in orders:
        try:
            numbers.append(int(order["id"]))
        except (TypeError, ValueError, KeyError):
            continue
    return str((max(numbers) if numbers else 0) + 1)


def public_orders(limit: int = 50) -> list[dict]:
    with _csv_lock:
        orders = read_all_orders()
    orders.reverse()
    return orders[:limit]


def detect(image):
    start = time.time()
    results = _model.predict(
        source=image,
        conf=_conf,
        iou=_iou,
        agnostic_nms=True,
        max_det=60,
        verbose=False,
    )[0]
    elapsed = time.time() - start

    class_names = [results.names[i] for i in sorted(results.names.keys())]
    boxes = []
    for box in results.boxes:
        cls_id = int(box.cls.item())
        boxes.append({
            "flavor": results.names[cls_id],
            "confidence": float(box.conf.item()),
            "bbox": box.xyxy[0].tolist(),
        })
    counts = Counter(box["flavor"] for box in boxes)
    items = format_items(counts)
    annotated = draw_predictions(image, boxes, class_names)
    return items, sum(counts.values()), elapsed, annotated


@app.after_request
def add_cors(response):
    # Reflect the origin ONLY when it matches the allowed frontend, instead
    # of a blanket "*" - a request from anywhere else gets no CORS headers
    # at all, so the browser blocks it client-side.
    origin = request.headers.get("Origin", "")
    if origin.rstrip("/") == ALLOWED_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


def mint_assemblyai_token() -> str:
    api_key = os.getenv("SPEECH_TO_TEXT_API_KEY")
    if not api_key:
        raise ValueError("SPEECH_TO_TEXT_API_KEY is not configured")

    token_url = "https://streaming.assemblyai.com/v3/token?" + urlencode({
        "expires_in_seconds": 60,
    })
    req = urllib_request.Request(
        token_url,
        headers={
            "Authorization": api_key,
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib_request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    token = data.get("token")
    if not token:
        raise ValueError("AssemblyAI token endpoint did not return a token")
    return token


@app.get("/api/assemblyai-token")
def api_assemblyai_token():
    try:
        return jsonify({"token": mint_assemblyai_token()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/flavors")
def api_flavors():
    return jsonify({"flavors": flavor_catalog()})


@app.get("/api/orders")
def api_orders():
    return jsonify({"orders": public_orders()})


@app.delete("/api/orders")
def api_delete_orders():
    with _csv_lock:
        write_all_orders([])
    return jsonify({"orders": []})


@app.delete("/api/orders/<order_id>")
def api_delete_order(order_id):
    with _csv_lock:
        orders = read_all_orders()
        remaining = [order for order in orders if str(order["id"]) != str(order_id)]
        if len(remaining) == len(orders):
            return jsonify({"error": "Order not found"}), 404
        write_all_orders(remaining)
    return jsonify({"deleted_id": str(order_id)})


@app.post("/api/orders")
def api_create_order():
    payload = request.get_json(silent=True) or {}
    try:
        items = normalize_items(payload.get("items"))
        transcript_items = normalize_items(payload.get("transcript_items", items))
        camera_items = normalize_items(payload.get("camera_items", items)) if payload.get("camera_items") else []
        photo_id = attach_photo_id(payload.get("photo_id"))
        box_size = parse_box_size(payload.get("box_size"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    with _csv_lock:
        orders = read_all_orders()
        order = {
            "id": next_order_id(orders),
            "timestamp": timestamp,
            "total_pieces": total_pieces(items),
            "items": items,
            "items_text": items_csv_cell(items),
            "photo_id": photo_id,
            "has_photo": photo_exists(photo_id),
            "box_size": box_size,
            "transcript_items": transcript_items,
            "camera_items": camera_items,
            "comparison_status": str(payload.get("comparison_status") or "match"),
            "pack_time_seconds": float(payload.get("pack_time_seconds")) if payload.get("pack_time_seconds") is not None else None,
        }
        orders.append(order)
        write_all_orders(orders)
    return jsonify({"order": order})


@app.put("/api/orders/<order_id>")
def api_update_order(order_id):
    payload = request.get_json(silent=True) or {}
    try:
        items = normalize_items(payload.get("items"))
        box_size = parse_box_size(payload.get("box_size")) if "box_size" in payload else None
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    with _csv_lock:
        orders = read_all_orders()
        updated = None
        for order in orders:
            if str(order["id"]) == str(order_id):
                order["items"] = items
                order["total_pieces"] = total_pieces(items)
                order["items_text"] = items_csv_cell(items)
                if "box_size" in payload:
                    order["box_size"] = box_size
                if payload.get("comparison_status") in ("match", "mismatch"):
                    order["comparison_status"] = payload["comparison_status"]
                updated = order
                break
        if updated is None:
            return jsonify({"error": "Order not found"}), 404
        write_all_orders(orders)
    return jsonify({"order": updated})


@app.post("/api/scan")
def api_scan():
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        return jsonify({"error": "No image uploaded"}), 400

    try:
        image = decode_image(upload.read())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    items, total, elapsed, annotated = detect(image)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

    photo_id = new_photo_id()
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(photo_file(photo_id, "capture")), image)
    cv2.imwrite(str(photo_file(photo_id, "annotated")), annotated)

    return jsonify({
        "timestamp": timestamp,
        "total_pieces": total,
        "items": items,
        "inference_seconds": round(elapsed, 3),
        "photo_id": photo_id,
        "annotated_image": encode_jpeg(annotated),
    })


@app.get("/api/orders/<order_id>/photo/<kind>")
def api_order_photo(order_id, kind):
    if kind not in ("capture", "annotated"):
        return jsonify({"error": "Unknown photo"}), 404
    with _csv_lock:
        orders = read_all_orders()
    order = next((row for row in orders if str(row["id"]) == str(order_id)), None)
    if order is None or not photo_exists(order.get("photo_id", "")):
        return jsonify({"error": "Photo not found"}), 404
    path = photo_file(order["photo_id"], kind)
    if not path.is_file() and kind == "annotated":
        path = photo_file(order["photo_id"], "capture")
    if not path.is_file():
        return jsonify({"error": "Photo not found"}), 404
    return send_from_directory(CAPTURE_DIR, path.name)


def send_frontend(asset="index.html"):
    if asset.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    if not DIST_DIR.exists():
        return (
            "React UI is not built. From frontend/ run `npm install` then "
            "`npm run dev` (http://127.0.0.1:5173), or `npm run build` and reload.",
            503,
        )
    target = DIST_DIR / asset
    if asset and target.is_file():
        return send_from_directory(DIST_DIR, asset)
    return send_from_directory(DIST_DIR, "index.html")


@app.get("/")
def index():
    return send_frontend("index.html")


@app.get("/<path:asset>")
def frontend_asset(asset):
    return send_frontend(asset)


def main():
    global _conf, _iou
    use_repo_root()
    parser = argparse.ArgumentParser(description="Chocolate Vision checkout web app")
    parser.add_argument("--weights", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--conf_threshold", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.4)
    args = parser.parse_args()

    _conf = args.conf_threshold
    _iou = args.iou
    weights = str(Path(args.weights)) if args.weights else default_weights()
    if not Path(weights).exists() and not str(weights).startswith("yolov8"):
        raise SystemExit(f"'{weights}' not found")
    load_model(weights)

    if str(weights).startswith("yolov8"):
        print(
            "No custom trained checkpoint was found; using the base YOLO model "
            f"{weights}. For best results, place a trained weights file in "
            "runs/detect/.../weights/best.pt or pass --weights."
        )

    print(f"Orders CSV: {ORDERS_CSV}")
    print(f"API: http://{args.host}:{args.port}")
    print(f"Allowed frontend origin (CORS): {ALLOWED_ORIGIN}")
    print("React UI: cd frontend && npm run dev  ->  http://127.0.0.1:5173")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()