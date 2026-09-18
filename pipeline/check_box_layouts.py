"""
Find the cavity grid in every empty-box photo and let you eyeball it
======================================================================

Run this once before generating a dataset. For each photo in
empty_box_photos/ it locates the insert and its cavities, writes an
overlay you can check by eye, and caches the result in box_layouts.json
so the generator doesn't redo the work 1500 times.

    python pipeline/check_box_layouts.py

Open box_layouts_check/*.jpg. Every red dot should sit in a cavity and
every yellow quad should hug one. If a box is wrong, nudge it:

    python pipeline/check_box_layouts.py --only 6 --nudge_x 0.01 --nudge_y -0.02

...where the numbers are fractions of a cavity: --nudge_x 0.01 shifts
the whole grid right by 1% of a cell width. --grow_x / --grow_y scale
the spacing the same way. Nudges are saved into the cache, so the
generator picks them up.

The old extract_tray_background.py cropped the insert out into a flat
background image. That isn't needed any more - the generator now pastes
pieces straight onto the full photo using the perspective it measured
here, so the lid, the rim and the counter all stay in the frame where
they belong.
"""

import argparse
import json
import re
from pathlib import Path

import cv2

from paths import ROOT, use_repo_root
from tray_layout import (detect_at_scale, draw_layout, layout_from_record,
                         layout_to_record)

BOX_LAYOUTS = {
    6: {"rows": 2, "cols": 3},
    10: {"rows": 2, "cols": 5},
    16: {"rows": 4, "cols": 4},
    30: {"rows": 5, "cols": 6},
    50: {"rows": 5, "cols": 10},
}

SIZE_RE = re.compile(r"(\d+)\s*[_-]?piece", re.I)
CACHE_PATH = ROOT / "box_layouts.json"


def parse_box_size(path):
    match = SIZE_RE.search(Path(path).stem)
    return int(match.group(1)) if match else None


def load_cache(path=CACHE_PATH):
    if Path(path).exists():
        return json.loads(Path(path).read_text())
    return {}


def save_cache(cache, path=CACHE_PATH):
    Path(path).write_text(json.dumps(cache, indent=2))


def nudge_record(record, dx, dy, grow_x, grow_y):
    """Shift/scale the cached grid, in units of one cavity."""
    cells = record["cells"]
    cx0 = sum(c[0] for c in cells) / len(cells)
    cy0 = sum(c[1] for c in cells) / len(cells)
    moved = []
    for cx, cy, cw, ch in cells:
        cx = cx0 + (cx - cx0) * grow_x + dx * cw
        cy = cy0 + (cy - cy0) * grow_y + dy * ch
        moved.append([cx, cy, cw * grow_x, ch * grow_y])
    record["cells"] = moved
    return record


def main():
    use_repo_root()
    parser = argparse.ArgumentParser(description="Detect and verify box cavity grids")
    parser.add_argument("--photo_dir", default="empty_box_photos")
    parser.add_argument("--out_dir", default="box_layouts_check")
    parser.add_argument("--cache", default=str(CACHE_PATH))
    parser.add_argument("--only", type=int, help="Only process this box size")
    parser.add_argument("--redetect", action="store_true",
                        help="Ignore the cache and detect from scratch")
    parser.add_argument("--nudge_x", type=float, default=0.0,
                        help="Shift the grid sideways, in cavity widths")
    parser.add_argument("--nudge_y", type=float, default=0.0,
                        help="Shift the grid up/down, in cavity heights")
    parser.add_argument("--grow_x", type=float, default=1.0,
                        help="Scale the horizontal spacing about the grid centre")
    parser.add_argument("--grow_y", type=float, default=1.0,
                        help="Scale the vertical spacing about the grid centre")
    args = parser.parse_args()

    photo_dir, out_dir = Path(args.photo_dir), Path(args.out_dir)
    if not photo_dir.exists():
        raise SystemExit(f"'{photo_dir}' does not exist")
    photos = sorted(p for p in photo_dir.iterdir()
                    if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not photos:
        raise SystemExit(f"No images in '{photo_dir}'")

    out_dir.mkdir(parents=True, exist_ok=True)
    cache = {} if args.redetect else load_cache(args.cache)
    adjusting = (args.nudge_x or args.nudge_y
                 or args.grow_x != 1.0 or args.grow_y != 1.0)

    for path in photos:
        size = parse_box_size(path)
        if size is None or size not in BOX_LAYOUTS:
            print(f"  skip {path.name}: filename doesn't say how many pieces")
            continue
        if args.only is not None and size != args.only:
            continue
        rows, cols = BOX_LAYOUTS[size]["rows"], BOX_LAYOUTS[size]["cols"]

        image = cv2.imread(str(path))
        if image is None:
            print(f"  skip {path.name}: unreadable")
            continue

        record = cache.get(path.name)
        if record is None or record["rows"] != rows or record["cols"] != cols:
            found = detect_at_scale(image, rows, cols)
            if found is None:
                print(f"  {path.name}: could not find the gold rim / insert")
                continue
            layout, work = found
            record = layout_to_record(layout, work.shape)
        if adjusting:
            record = nudge_record(record, args.nudge_x, args.nudge_y,
                                  args.grow_x, args.grow_y)
        cache[path.name] = record

        scale = min(1.0, 1400 / max(image.shape[:2]))
        preview = cv2.resize(image, None, fx=scale, fy=scale)
        layout = layout_from_record(record, preview.shape)
        cv2.imwrite(str(out_dir / f"{path.stem}.jpg"), draw_layout(preview, layout))
        print(f"  {path.name}: {rows}x{cols} grid, fit score {record['score']:.3f}")

    save_cache(cache, args.cache)
    print(f"\nLayouts cached in '{args.cache}'. Overlays in '{out_dir}/'.")
    print("Red dots should be in cavities. If one box is off, nudge it, e.g.:")
    print("  python pipeline/check_box_layouts.py --only 6 --nudge_y 0.15")
    print("Then generate the dataset:")
    print("  python pipeline/generate_training_data_boxsize.py --n_per_size 300")


if __name__ == "__main__":
    main()
