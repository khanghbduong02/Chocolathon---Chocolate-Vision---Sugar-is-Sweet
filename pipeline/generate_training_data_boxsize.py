"""
Generate Box-Size-Aware Synthetic Training Data
==================================================

Fills real empty-box photos with real chocolate crops, one piece per
cavity, and writes YOLO labels. Crops come from
automated_raw_pieces/<flavor>/*.png, where <flavor> is the slug from
labels.json (confetti_cake, amaretto, ...).

Where the cavities are comes from tray_layout.py, which fits the insert
as a quadrilateral and finds the cavity lattice inside it. That matters:
the photos are hand-held, so the insert is never square-on, and the far
row of cavities is visibly smaller than the near row. Pieces are scaled
per cavity from that measured geometry and painted back-to-front, so a
near piece can overlap the one behind it the way it does in a real box.

Run check_box_layouts.py first - it caches the geometry in
box_layouts.json and writes overlays you can verify by eye. Without the
cache this script detects the layout itself, once per photo.

Each finished image is then put through a random stretch: anisotropic
scale, small rotation, and a perspective corner jitter. That is what
gives the set a range of camera angles from only five photos. Labels are
read off an instance map that goes through the same warp, so they stay
exact no matter how hard the image is pushed around, and they describe
the visible part of each piece rather than its full silhouette.

GRID LAYOUTS
------------
    6-piece:  2 rows x 3 cols        30-piece: 5 rows x 6 cols
    10-piece: 2 rows x 5 cols        50-piece: 5 rows x 10 cols
    16-piece: 4 rows x 4 cols

OUTPUT
------
synthetic_dataset/
    images/synth_box6_00000.jpg ...
    labels/synth_box6_00000.txt ...   (YOLO format)
    classes.txt
    preview/...                       (--preview, boxes drawn on)

USAGE
-----
    python pipeline/check_box_layouts.py
    python pipeline/generate_training_data_boxsize.py --n_per_size 300 --preview 8
"""

import argparse
import random
from pathlib import Path

import albumentations as A
import cv2
import numpy as np

from check_box_layouts import BOX_LAYOUTS, load_cache, parse_box_size, save_cache
from tray_layout import detect_at_scale, layout_from_record, layout_to_record


def load_pieces_by_class(raw_dir):
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        raise SystemExit(f"'{raw_dir}' doesn't exist. Run auto_crop_pieces.py first "
                         f"to populate it with piece crops.")
    pieces_by_class = {}
    class_names = sorted([d.name for d in raw_dir.iterdir()
                          if d.is_dir() and not d.name.startswith("_")])

    for class_name in class_names:
        pieces = []
        for img_path in (raw_dir / class_name).glob("*.png"):
            if "debug" in img_path.stem:
                continue
            rgba = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
            if rgba is None or rgba.shape[2] != 4:
                continue
            pieces.append((rgba[:, :, :3], rgba[:, :, 3]))
        pieces_by_class[class_name] = pieces
        print(f"  '{class_name}': {len(pieces)} piece crops available")

    return pieces_by_class, class_names


def paste_piece(canvas, ids, piece_bgr, piece_alpha, cx, cy, cavity_w, cavity_h,
                angle, instance_id):
    """Drop one piece into a cavity and stamp its id into the instance map.

    Sized off the cavity width rather than fitted to the whole cavity
    box: a chocolate stands proud of the tray, so in a tilted photo it
    covers more height than the cavity's footprint does. Keeping the
    crop's own aspect ratio preserves that, capped so a stray tall crop
    can't tower over the box.
    """
    ph, pw = piece_bgr.shape[:2]
    scale = (cavity_w / pw) * random.uniform(0.94, 1.12)
    if ph * scale > 2.2 * cavity_h:
        scale = 2.2 * cavity_h / ph
    new_w, new_h = max(1, int(pw * scale)), max(1, int(ph * scale))

    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    piece = cv2.resize(piece_bgr, (new_w, new_h), interpolation=interp)
    alpha = cv2.resize(piece_alpha, (new_w, new_h), interpolation=interp)

    rot = cv2.getRotationMatrix2D((new_w / 2, new_h / 2), angle, 1.0)
    piece = cv2.warpAffine(piece, rot, (new_w, new_h), borderValue=0)
    alpha = cv2.warpAffine(alpha, rot, (new_w, new_h), borderValue=0)

    ch, cw = canvas.shape[:2]
    x0, y0 = int(round(cx - new_w / 2)), int(round(cy - new_h / 2))
    src_x0, src_y0 = max(0, -x0), max(0, -y0)
    dst_x0, dst_y0 = max(0, x0), max(0, y0)
    dst_x1, dst_y1 = min(cw, x0 + new_w), min(ch, y0 + new_h)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return False
    src_x1 = src_x0 + (dst_x1 - dst_x0)
    src_y1 = src_y0 + (dst_y1 - dst_y0)

    a = alpha[src_y0:src_y1, src_x0:src_x1]
    region = canvas[dst_y0:dst_y1, dst_x0:dst_x1].astype(np.float32)
    crop = piece[src_y0:src_y1, src_x0:src_x1].astype(np.float32)
    weight = (a.astype(np.float32) / 255.0)[..., None]
    canvas[dst_y0:dst_y1, dst_x0:dst_x1] = (weight * crop + (1 - weight) * region).astype(np.uint8)
    ids[dst_y0:dst_y1, dst_x0:dst_x1][a > 127] = instance_id
    return True


def random_view_matrix(w, h, keep, stretch=0.16, perspective=0.045, rotate=7.0):
    """A random 'photographed from somewhere else' transform.

    Built as a crop rather than a warp of the whole frame: a rotated,
    perspective-skewed quadrilateral inside the photo is stretched out
    to fill the output. Every output pixel then comes from real image
    content, with no mirrored counter-top pasted along the edges. Taking
    the horizontal and vertical crop independently is what squashes the
    box one way or the other, which is the point - five photos have five
    camera angles, and the detector needs more than that.
    """
    low, high = 0.02, min(0.02 + 2 * stretch, 0.25)
    # never crop into the filled tray itself, however wide the box is
    keep_x0, keep_y0, keep_x1, keep_y1 = keep
    room_x = max(0.0, 0.7 * min(keep_x0, w - keep_x1))
    room_y = max(0.0, 0.7 * min(keep_y0, h - keep_y1))
    inset_x = min(random.uniform(low, high) * w, room_x)
    inset_y = min(random.uniform(low, high) * h, room_y)
    corners = np.array([[inset_x, inset_y], [w - inset_x, inset_y],
                        [w - inset_x, h - inset_y], [inset_x, h - inset_y]], np.float32)

    angle = np.deg2rad(random.uniform(-rotate, rotate))
    rotation = np.array([[np.cos(angle), -np.sin(angle)],
                         [np.sin(angle), np.cos(angle)]], np.float32)
    center = np.array([w / 2, h / 2], np.float32)
    corners = (corners - center) @ rotation.T + center

    jitter = perspective * min(w, h)
    corners += np.random.uniform(-jitter, jitter, corners.shape).astype(np.float32)
    full = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    return cv2.getPerspectiveTransform(corners, full)


def apply_view(image, ids, matrix):
    h, w = image.shape[:2]
    warped = cv2.warpPerspective(image, matrix, (w, h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
    warped_ids = cv2.warpPerspective(ids, matrix, (w, h), flags=cv2.INTER_NEAREST,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return warped, warped_ids


def boxes_from_ids(ids, count):
    """Tight box around every instance still visible, keyed by id."""
    ys, xs = np.nonzero(ids)
    if not len(ys):
        return {}
    values = ids[ys, xs]
    x0 = np.full(count + 1, np.inf)
    y0 = np.full(count + 1, np.inf)
    x1 = np.full(count + 1, -np.inf)
    y1 = np.full(count + 1, -np.inf)
    np.minimum.at(x0, values, xs)
    np.minimum.at(y0, values, ys)
    np.maximum.at(x1, values, xs)
    np.maximum.at(y1, values, ys)
    boxes = {}
    for i in range(1, count + 1):
        if not np.isfinite(x0[i]):
            continue
        boxes[i] = (float(x0[i]), float(y0[i]), float(x1[i] + 1), float(y1[i] + 1))
    return boxes


def get_photometric_augmentation():
    return A.Compose([
        A.RandomBrightnessContrast(brightness_limit=0.25, contrast_limit=0.25, p=0.8),
        A.HueSaturationValue(hue_shift_limit=8, sat_shift_limit=20, val_shift_limit=15, p=0.5),
        A.GaussianBlur(blur_limit=(1, 3), p=0.3),
        A.GaussNoise(std_range=(0.03, 0.1), p=0.3),
        A.ImageCompression(quality_range=(70, 100), p=0.4),
    ])


def prepare_backgrounds(bg_dir, canvas_size, cache):
    """Load each empty-box photo once, with its cavity geometry."""
    bg_dir = Path(bg_dir)
    paths = sorted(p for p in bg_dir.glob("*")
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and "debug" not in p.stem)
    by_size, dirty = {}, False
    for path in paths:
        size = parse_box_size(path)
        if size is None or size not in BOX_LAYOUTS:
            print(f"  skipping {path.name}: filename doesn't say how many pieces")
            continue
        image = cv2.imread(str(path))
        if image is None:
            continue
        rows = BOX_LAYOUTS[size]["rows"]
        cols = BOX_LAYOUTS[size]["cols"]

        record = cache.get(path.name)
        if record is None or record["rows"] != rows or record["cols"] != cols:
            found = detect_at_scale(image, rows, cols)
            if found is None:
                print(f"  skipping {path.name}: could not find the insert")
                continue
            layout, work = found
            record = layout_to_record(layout, work.shape)
            cache[path.name] = record
            dirty = True

        scale = min(1.0, canvas_size / max(image.shape[:2]))
        photo = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1.0 else image
        layout = layout_from_record(record, photo.shape)
        by_size.setdefault(size, []).append((path.name, photo, layout.cells_in_photo()))
        print(f"  {path.name}: {rows}x{cols} cavities, {photo.shape[1]}x{photo.shape[0]} px")
    return by_size, dirty


def compose_box(photo, cavities, pieces_by_class, class_names, class_to_id,
                tilt, view_kwargs):
    """One filled box: returns (image, labels) with labels in YOLO form."""
    canvas = photo.copy()
    ids = np.zeros(canvas.shape[:2], np.int32)
    id_to_class = {}

    # far cavities first, so a near piece overlaps the one behind it
    for slot, (cx, cy, cw, ch) in enumerate(sorted(cavities, key=lambda c: c[1]), start=1):
        class_name = random.choice(class_names)
        piece_bgr, piece_alpha = random.choice(pieces_by_class[class_name])
        jitter_x = random.uniform(-0.07, 0.07) * cw
        jitter_y = random.uniform(-0.07, 0.07) * ch
        if paste_piece(canvas, ids, piece_bgr, piece_alpha,
                       cx + jitter_x, cy + jitter_y, cw, ch,
                       random.uniform(-tilt, tilt), slot):
            id_to_class[slot] = class_to_id[class_name]

    if view_kwargs is not None:
        keep = (min(c[0] - c[2] / 2 for c in cavities),
                min(c[1] - c[3] / 2 for c in cavities),
                max(c[0] + c[2] / 2 for c in cavities),
                max(c[1] + c[3] / 2 for c in cavities))
        matrix = random_view_matrix(canvas.shape[1], canvas.shape[0], keep, **view_kwargs)
        canvas, ids = apply_view(canvas, ids, matrix)

    h, w = canvas.shape[:2]
    labels = []
    for instance, (x0, y0, x1, y1) in boxes_from_ids(ids, len(cavities)).items():
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        labels.append((id_to_class[instance], (x0 + x1) / 2 / w, (y0 + y1) / 2 / h,
                       (x1 - x0) / w, (y1 - y0) / h))
    return canvas, labels


def draw_preview(image, labels, class_names):
    vis = image.copy()
    h, w = vis.shape[:2]
    for class_id, cx, cy, bw, bh in labels:
        x0, y0 = int((cx - bw / 2) * w), int((cy - bh / 2) * h)
        x1, y1 = int((cx + bw / 2) * w), int((cy + bh / 2) * h)
        cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 255, 0), 2)
        cv2.putText(vis, class_names[class_id], (x0, max(12, y0 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    return vis


def generate_dataset(raw_dir, bg_dir, out_dir, n_per_size, canvas_size, tilt,
                     view_kwargs, n_preview):
    out_dir = Path(out_dir)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "labels").mkdir(parents=True, exist_ok=True)
    if n_preview:
        (out_dir / "preview").mkdir(parents=True, exist_ok=True)

    print("Loading piece crops...")
    pieces_by_class, class_names = load_pieces_by_class(raw_dir)
    usable = [c for c in class_names if pieces_by_class[c]]
    if not usable:
        raise SystemExit(f"No 4-channel piece crops found in '{raw_dir}'. "
                         f"Run auto_crop_pieces.py first.")
    (out_dir / "classes.txt").write_text("\n".join(class_names))
    class_to_id = {name: i for i, name in enumerate(class_names)}

    print("\nLoading empty-box photos...")
    cache = load_cache()
    by_size, dirty = prepare_backgrounds(bg_dir, canvas_size, cache)
    if dirty:
        save_cache(cache)
    if not by_size:
        raise SystemExit(f"No usable empty-box photos in '{bg_dir}'. They need names "
                         f"like box_6_piece.jpg so the grid is known.")

    photometric = get_photometric_augmentation()
    index, previews = 0, 0
    for box_size, backgrounds in sorted(by_size.items()):
        print(f"\nGenerating {n_per_size} '{box_size}-piece' boxes from "
              f"{len(backgrounds)} photo(s)...")
        for _ in range(n_per_size):
            _, photo, cavities = random.choice(backgrounds)
            image, labels = compose_box(photo, cavities, pieces_by_class, usable,
                                        class_to_id, tilt, view_kwargs)
            image = photometric(image=image)["image"]

            name = f"synth_box{box_size}_{index:05d}"
            cv2.imwrite(str(out_dir / "images" / f"{name}.jpg"), image)
            with open(out_dir / "labels" / f"{name}.txt", "w") as f:
                for class_id, cx, cy, bw, bh in labels:
                    f.write(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")
            if previews < n_preview:
                cv2.imwrite(str(out_dir / "preview" / f"{name}.jpg"),
                            draw_preview(image, labels, class_names))
                previews += 1
            index += 1

    print(f"\nDone. {index} images written to {out_dir}/")
    print(f"Classes ({len(class_names)}): {class_names}")
    if n_preview:
        print(f"Check {out_dir}/preview/ - green boxes should hug the chocolates.")


def default_raw_dir():
    auto = Path("automated_raw_pieces")
    if auto.exists() and any(auto.glob("*/*.png")):
        return str(auto)
    raise SystemExit("No piece crops in automated_raw_pieces/. Run auto_crop_pieces.py first.")


if __name__ == "__main__":
    from paths import use_repo_root
    use_repo_root()
    parser = argparse.ArgumentParser(description="Generate box-size-aware synthetic training data")
    parser.add_argument("--raw_dir", default=default_raw_dir(),
                        help="Folder of per-flavor piece crops (4-channel PNG)")
    parser.add_argument("--bg_dir", default="empty_box_photos",
                        help="Empty-box photos named box_<N>_piece.jpg")
    parser.add_argument("--out_dir", default="synthetic_dataset")
    parser.add_argument("--n_per_size", type=int, default=300,
                        help="How many synthetic images to generate PER box size")
    parser.add_argument("--canvas_size", type=int, default=1280,
                        help="Long side of each output image, in pixels")
    parser.add_argument("--tilt", type=float, default=12.0,
                        help="Max rotation of a piece within its cavity, degrees")
    parser.add_argument("--stretch", type=float, default=0.16,
                        help="Max anisotropic squash/stretch, as a fraction")
    parser.add_argument("--perspective", type=float, default=0.045,
                        help="Max corner displacement, as a fraction of the short side")
    parser.add_argument("--rotate", type=float, default=7.0,
                        help="Max whole-image rotation, degrees")
    parser.add_argument("--no_warp", action="store_true",
                        help="Skip the stretch/perspective augmentation entirely")
    parser.add_argument("--preview", type=int, default=0,
                        help="Write this many label-annotated previews")
    args = parser.parse_args()

    view = None if args.no_warp else {"stretch": args.stretch,
                                      "perspective": args.perspective,
                                      "rotate": args.rotate}
    generate_dataset(args.raw_dir, args.bg_dir, args.out_dir, args.n_per_size,
                     args.canvas_size, args.tilt, view, args.preview)
