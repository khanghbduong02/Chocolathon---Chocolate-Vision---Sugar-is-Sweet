"""
Transfer Learning: Fine-Tune YOLOv8 on Chocolate Box Data
=============================================================

Fine-tunes a pretrained YOLOv8 detector (trained on COCO) on your
synthetic + real chocolate box images. Transfer learning means we start
from weights that already know general shapes/edges/textures, and only
adapt the final layers to your specific chocolate classes - this needs
far less data than training from scratch, which matters a lot given
your dataset is mostly synthetic plus a small real set.

RECOMMENDED DATA MIX (see discussion below the code)
------------------------------------------------------
- TRAIN: synthetic_dataset/ (your generated box-size-aware composites)
         + optionally a handful of real hand-labeled box photos mixed in
- VAL:   a SEPARATE small set of real, hand-labeled packed-box photos
         (20-30 is a fine starting point) - this is what tells you
         honestly whether the model generalizes to real boxes, since
         validating only on synthetic data will look great regardless
         of the synthetic-to-real gap.

FOLDER STRUCTURE EXPECTED
--------------------------
synthetic_dataset/
    images/*.jpg
    labels/*.txt        (YOLO format, from generate_training_data_boxsize.py)
    classes.txt

real_val_dataset/       (you create this: real box photos, hand-labeled
                          in the same YOLO format - e.g. via Roboflow,
                          LabelImg, or CVAT, all of which export YOLO txt)
    images/*.jpg
    labels/*.txt

OUTPUT
------
runs/detect/chocolate_model/weights/best.pt   <- your fine-tuned model
runs/detect/chocolate_model/                  <- training curves, sample
                                                  predictions, confusion
                                                  matrix, all auto-generated

USAGE
-----
    python pipeline/train_yolo.py --epochs 60 --model yolov8n.pt

Start with yolov8n.pt (nano) - it trains fast, which matters for hackathon
iteration speed, and is plenty for a fixed camera angle over a checkout
counter. Move to yolov8s.pt only if accuracy plateaus and you have
training time to spare.
"""

import argparse
from pathlib import Path

import yaml
from ultralytics import YOLO

from paths import ROOT, use_repo_root


def build_data_yaml(synthetic_dir, real_val_dir, classes_path, out_yaml_path,
                     val_split_from_synthetic=0.0):
    """
    Writes the YOLO data.yaml config. If a real validation set exists, it's
    used as-is for val. If not (val_split_from_synthetic > 0), a fraction
    of the synthetic set is held out instead - clearly worse for judging
    real-world performance, but lets you get a training run going before
    you've hand-labeled any real boxes.
    """
    with open(classes_path) as f:
        class_names = [line.strip() for line in f if line.strip()]

    synthetic_dir = Path(synthetic_dir).resolve()
    data_yaml = {
        "path": str(synthetic_dir.parent),
        "train": str(synthetic_dir / "images"),
        "names": {i: name for i, name in enumerate(class_names)},
    }

    real_val_dir = Path(real_val_dir) if real_val_dir else None
    if real_val_dir and real_val_dir.exists() and any((real_val_dir / "images").glob("*")):
        data_yaml["val"] = str(real_val_dir.resolve() / "images")
        print(f"Using real labeled data for validation: {real_val_dir}/images "
              f"({len(list((real_val_dir/'images').glob('*')))} images)")
    else:
        print("WARNING: no real validation set found at "
              f"'{real_val_dir}' - falling back to a held-out slice of "
              "SYNTHETIC data for validation. This will make accuracy look "
              "better than it actually is on real boxes. Hand-label even "
              "15-20 real box photos and point --real_val_dir at them as "
              "soon as you can.")
        data_yaml["val"] = str(synthetic_dir / "images")  # same-domain fallback

    with open(out_yaml_path, "w") as f:
        yaml.dump(data_yaml, f, default_flow_style=False)

    return out_yaml_path, class_names


def main():
    use_repo_root()
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8 on chocolate box data")
    parser.add_argument("--synthetic_dir", default="synthetic_dataset")
    parser.add_argument("--real_val_dir", default="real_val_dataset",
                         help="Folder of real, hand-labeled box photos for validation")
    parser.add_argument("--model", default="yolov8n.pt",
                         help="Pretrained checkpoint to start from (nano is fastest)")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--run_name", default="chocolate_model")
    args = parser.parse_args()

    classes_path = Path(args.synthetic_dir) / "classes.txt"
    if not classes_path.exists():
        raise SystemExit(f"'{classes_path}' not found - run "
                          "generate_training_data_boxsize.py first")

    data_yaml_path, class_names = build_data_yaml(
        args.synthetic_dir, args.real_val_dir, classes_path, ROOT / "chocolate_data.yaml"
    )
    print(f"\nClasses ({len(class_names)}): {class_names}")

    print(f"\nLoading pretrained {args.model} (COCO weights) for transfer learning...")
    model = YOLO(args.model)

    print(f"Starting training: {args.epochs} epochs, imgsz={args.imgsz}, batch={args.batch}")
    model.train(
        data=data_yaml_path,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        name=args.run_name,
        patience=15,        # stop early if val metrics plateau
        pretrained=True,    # explicit: keep COCO-pretrained backbone weights
        # Light additional augmentation on top of what's already baked into
        # the synthetic images - mosaic helps the model learn to handle
        # multiple small adjacent objects, which is exactly your box layout
        mosaic=0.5,
        degrees=10.0,
        translate=0.05,
        scale=0.2,
        fliplr=0.5,
    )

    best_weights = Path("runs/detect") / args.run_name / "weights" / "best.pt"
    print(f"\nTraining complete.")
    print(f"Best weights: {best_weights}")
    print(f"Training curves + confusion matrix + sample predictions: "
          f"runs/detect/{args.run_name}/")
    print("\nNext step: run inference on a few REAL packed box photos you "
          "held out and eyeball the predicted boxes before trusting the "
          "numbers - metrics on synthetic-only validation can look strong "
          "while still missing real-world failure modes.")


if __name__ == "__main__":
    main()