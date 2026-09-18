"""
Run Inference: Photo of a Box -> One Record (+ Visual Check)
=================================================================

This is the actual deliverable the hackathon is asking for: point this at
a photo of a packed box, get back one record of which pieces are in it
and how many, exportable as JSON/CSV. It also draws the predicted boxes
on the image so you can eyeball whether the model is actually right,
which matters more than the raw mAP number at this stage.

USAGE
-----
Single photo:
    python pipeline/predict_box.py --weights runs/detect/chocolate_model-2/weights/best.pt --image real_boxes/box1.jpg

Folder of photos (e.g. your held-out real test boxes):
    python pipeline/predict_box.py --weights runs/detect/chocolate_model-2/weights/best.pt --image_dir real_boxes/

OUTPUT
------
predictions/
    box1_annotated.jpg     <- photo with predicted boxes drawn, for eyeballing
    box1_record.json       <- {"flavor": count, ...} + metadata
predictions/all_records.csv   <- one row per box, all flavors as columns (only
                                   written when using --image_dir on multiple images)

WHAT TO ACTUALLY DO WITH THIS
--------------------------------
1. Run it on your real held-out box photos (not synthetic ones - synthetic
   will look artificially good).
2. Open every *_annotated.jpg and check: did it miss any pieces? Double-count
   any? Mix up look-alike flavors? This is your honest "where it breaks"
   evidence for the writeup - screenshot the bad ones.
3. The printed inference time per image is your starting point for the
   "how many seconds does this add at the counter" metric - it's not the
   whole answer (you still need to time photo-taking + any manual
   correction step), but it's the automatable part.
"""

import argparse
import csv
import json
import time
from pathlib import Path
from collections import Counter

import cv2
from ultralytics import YOLO


def draw_predictions(image, boxes, class_names):
    """Draw bounding boxes + labels for visual inspection."""
    annotated = image.copy()
    colors = {}
    rng_seed = 42
    for i, name in enumerate(class_names):
        # deterministic-ish distinct colors per class
        colors[name] = (
            (37 * i + 17) % 255,
            (91 * i + 53) % 255,
            (149 * i + 89) % 255,
        )

    for box in boxes:
        x0, y0, x1, y1 = map(int, box["bbox"])
        color = colors.get(box["flavor"], (0, 255, 0))
        cv2.rectangle(annotated, (x0, y0), (x1, y1), color, 2)
        label = f"{box['flavor']} {box['confidence']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x0, y0 - th - 6), (x0 + tw + 4, y0), color, -1)
        cv2.putText(annotated, label, (x0 + 2, y0 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return annotated


def write_yolo_label(label_dir, image_path, boxes, image_shape, name_to_id):
    """Write detections as a YOLO-format .txt so they can be loaded into a
    labeling tool and corrected instead of drawn from scratch."""
    height, width = image_shape[:2]
    lines = []
    for box in boxes:
        cls_id = name_to_id.get(box["flavor"])
        if cls_id is None:
            continue
        x0, y0, x1, y1 = box["bbox"]
        # clip to the frame - warped/edge detections can run slightly outside
        x0, x1 = max(0.0, x0), min(float(width), x1)
        y0, y1 = max(0.0, y0), min(float(height), y1)
        if x1 <= x0 or y1 <= y0:
            continue
        lines.append(
            f"{cls_id} {(x0 + x1) / 2 / width:.6f} {(y0 + y1) / 2 / height:.6f} "
            f"{(x1 - x0) / width:.6f} {(y1 - y0) / height:.6f}"
        )

    label_dir.mkdir(parents=True, exist_ok=True)
    (label_dir / f"{image_path.stem}.txt").write_text("\n".join(lines) + "\n")


def predict_single(model, image_path, out_dir, conf_threshold,
                   iou=0.5, agnostic_nms=True, max_det=60, label_dir=None):
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"  Could not read {image_path}, skipping")
        return None

    start = time.time()
    # agnostic_nms matters a lot here: one chocolate should get exactly one
    # box, but per-class NMS happily lets two different flavors both claim
    # the same piece, which shows up as phantom extra pieces in the count.
    results = model.predict(source=str(image_path), conf=conf_threshold,
                            iou=iou, agnostic_nms=agnostic_nms,
                            max_det=max_det, verbose=False)[0]
    inference_seconds = time.time() - start

    class_names = [results.names[i] for i in sorted(results.names.keys())]

    boxes = []
    for box in results.boxes:
        cls_id = int(box.cls.item())
        boxes.append({
            "flavor": results.names[cls_id],
            "confidence": float(box.conf.item()),
            "bbox": box.xyxy[0].tolist(),  # x0, y0, x1, y1 in pixels
        })

    counts = Counter(b["flavor"] for b in boxes)
    total_pieces = sum(counts.values())

    record = {
        "source_image": str(image_path.name),
        "total_pieces_detected": total_pieces,
        "counts_by_flavor": dict(counts),
        "inference_seconds": round(inference_seconds, 3),
        "detections": boxes,  # full detail incl. confidence + bbox, in case you need it
    }

    stem = image_path.stem
    with open(out_dir / f"{stem}_record.json", "w") as f:
        json.dump(record, f, indent=2)

    annotated = draw_predictions(image, boxes, class_names)
    cv2.imwrite(str(out_dir / f"{stem}_annotated.jpg"), annotated)

    if label_dir is not None:
        name_to_id = {name: i for i, name in results.names.items()}
        write_yolo_label(Path(label_dir), image_path, boxes, image.shape, name_to_id)

    print(f"  {image_path.name}: {total_pieces} pieces detected in "
          f"{inference_seconds*1000:.0f} ms -> {dict(counts)}")

    return record


def main():
    from paths import use_repo_root
    use_repo_root()
    parser = argparse.ArgumentParser(description="Run the trained model on box photos")
    parser.add_argument("--weights", default="runs/detect/chocolate_model-2/weights/best.pt")
    parser.add_argument("--image", help="Single image to run inference on")
    parser.add_argument("--image_dir", help="Folder of images to run inference on")
    parser.add_argument("--out_dir", default="predictions")
    parser.add_argument("--conf_threshold", type=float, default=0.35,
                         help="Minimum confidence to count a detection - lower catches "
                              "more pieces but risks false positives; raise this if the "
                              "model is over-counting, lower it if it's missing pieces")
    parser.add_argument("--iou", type=float, default=0.5,
                         help="NMS overlap threshold - lower it to suppress more "
                              "duplicate boxes stacked on the same chocolate")
    parser.add_argument("--max_det", type=int, default=60,
                         help="Hard cap on pieces per photo")
    parser.add_argument("--per_class_nms", action="store_true",
                         help="Allow two different flavors to both box the same "
                              "piece (off by default, since one chocolate is one piece)")
    parser.add_argument("--save_yolo", metavar="DIR",
                         help="Also write YOLO-format .txt labels here, so these "
                              "predictions can be loaded into a labeling tool and "
                              "corrected instead of drawn from scratch")
    args = parser.parse_args()

    if not args.image and not args.image_dir:
        raise SystemExit("Provide either --image <file> or --image_dir <folder>")

    weights_path = Path(args.weights)
    if not weights_path.exists():
        raise SystemExit(f"'{weights_path}' not found - check the path to your "
                          f"trained weights from train_yolo.py")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading model from {weights_path}...")
    model = YOLO(str(weights_path))

    if args.save_yolo:
        # labeling tools need the class list in the same id order as the model
        label_dir = Path(args.save_yolo)
        label_dir.mkdir(parents=True, exist_ok=True)
        names = [model.names[i] for i in sorted(model.names.keys())]
        (label_dir / "classes.txt").write_text("\n".join(names) + "\n")
        print(f"Wrote class list: {label_dir / 'classes.txt'}")

    if args.image:
        image_paths = [Path(args.image)]
    else:
        image_dir = Path(args.image_dir)
        image_paths = sorted([p for p in image_dir.glob("*")
                               if p.suffix.lower() in [".jpg", ".jpeg", ".png",
                                                       ".webp", ".bmp", ".tif", ".tiff"]])
        if not image_paths:
            raise SystemExit(f"No images found in '{image_dir}'")

    print(f"Running inference on {len(image_paths)} image(s)...")
    records = []
    for image_path in image_paths:
        record = predict_single(model, image_path, out_dir, args.conf_threshold,
                                iou=args.iou,
                                agnostic_nms=not args.per_class_nms,
                                max_det=args.max_det,
                                label_dir=args.save_yolo)
        if record:
            records.append(record)

    # If multiple images, also write one combined CSV - one row per box,
    # one column per flavor seen across ALL boxes (0 where a flavor
    # wasn't detected in that box)
    if len(records) > 1:
        all_flavors = sorted({flavor for r in records for flavor in r["counts_by_flavor"]})
        csv_path = out_dir / "all_records.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["source_image", "total_pieces", "inference_seconds"] + all_flavors)
            for r in records:
                row = [r["source_image"], r["total_pieces_detected"], r["inference_seconds"]]
                row += [r["counts_by_flavor"].get(flavor, 0) for flavor in all_flavors]
                writer.writerow(row)
        print(f"\nCombined CSV written: {csv_path}")

    print(f"\nDone. Check {out_dir}/*_annotated.jpg for every box before trusting the counts.")


if __name__ == "__main__":
    main()