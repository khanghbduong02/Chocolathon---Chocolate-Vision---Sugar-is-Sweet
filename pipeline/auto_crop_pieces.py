"""
Automated Piece Extraction from Tray Photos (SAM-based)
==========================================================

WHY THIS EXISTS
----------------
click_to_crop.py works, but hand-drawing ~26 boxes per photo across 33
tray photos is roughly 850 drags. This script does the same job
automatically and leaves you with a verification step instead of a
drawing step - reviewing 26 thumbnails is much faster than drawing 26
boxes.

WHY SAM AND NOT COLOR THRESHOLDING
-----------------------------------
The tray photos are display-case shots: one flavor per white tray,
pieces packed in a grid, with OTHER flavors' trays visible around the
edges. Color thresholding needs a per-flavor rule (and fails outright on
white/cream pieces against a white tray), so instead this uses Segment
Anything (via ultralytics' `mobile_sam.pt`, ~39MB, downloads once then
runs offline) which finds object boundaries without knowing anything
about chocolate.

SAM in plain "segment everything" mode over-segments these pieces - a
glossy dome usually comes back as a separate top-highlight mask and a
lower shadow band rather than one whole piece. So this runs two passes:

    pass 1: everything-mode, only to get candidate seed POINTS
    pass 2: point-prompted SAM at each seed, which returns one coherent
            whole-object mask per piece

Then a coverage-filling round prompts any tray area that no accepted
mask covers yet, to pick up pieces the first round missed.

FILTERS APPLIED (in order)
---------------------------
1. Border touch     - masks running off the image edge are partial pieces
2. Extent           - a whole piece fills roughly 0.7 of its bounding box,
                      so anything much emptier is half a piece or the
                      star-shaped patch of bare tray between four of them
3. Solidity         - domes are convex; ragged part-piece-part-shadow
                      masks are not
4. Main tray        - pieces are clustered by spacing and only the
                      central, most populous tray is kept, so the
                      neighbouring trays visible at the edges of a
                      display-case shot don't leak their flavors into
                      this flavor's folder
5. Size window      - absolute sanity bounds, then a robust median/MAD
                      test so one piece isn't 3x its neighbours
6. Color consistency- one tray is one flavor, so a piece whose mean color
                      is far from the tray's median piece color is a
                      mis-grab (disable with --color_tol 0)

OUTPUT
------
automated_raw_pieces/
    <flavor>/
        auto_000.png ...        <- BGRA, alpha = SAM mask

automated_raw_pieces_review/    <- verification imagery, kept out of the
    <image>_overlay.jpg            pieces folder because the compositor
    <image>_sheet.jpg              treats every subfolder there as a class

    _overlay.jpg = accepted (green) / rejected (red) masks on the original
                   photo, each rejection labelled with its reason
    _sheet.jpg   = numbered contact sheet of every crop that was saved,
                   composited on a checkerboard so the alpha is visible

Crops are written as 4-channel BGRA at FULL photo resolution (the mask is
computed on a downscaled copy for speed, then upscaled). This matters:
generate_training_data_boxsize.py only loads 4-channel PNGs and silently
skips 3-channel ones, so these alpha cutouts also composite properly
instead of being pasted as opaque rectangles.

USAGE
-----
All tray photos, flavor taken from labels.json:
    python pipeline/auto_crop_pieces.py --image_dir tray_photos/

One photo:
    python pipeline/auto_crop_pieces.py --image tray_photos/confetti_cake.jpg

CORRECTING THE RESULT
----------------------
Two interactive passes, both optional:

    python pipeline/auto_crop_pieces.py --fix

    Corrects pieces on the tray photo itself:

        left-click a selected piece      drop it
        left-click an unselected piece   SAM segments it and adds it
        right-click two pieces in turn   fuse them into one piece
        middle-click (or shift+click)    split: shrink to the single
                                         piece under the cursor
        u / r / s / n / q                undo, reset, save+next, skip, quit

    Merge is for one chocolate that came back as a dome plus a separate
    shadow band. Split is the opposite: one mask covering two chocolates.
    Middle-click one of them to shrink the mask onto it, then middle-click
    the one left behind to recover it as its own piece.

    This is the better pass for "it missed one" or "that one isn't this
    flavor", because you see each piece in context on the tray.

    python pipeline/auto_crop_pieces.py --review

    Flips through the saved crops as thumbnails and deletes the ones you
    mark. Faster when you just want to bin obviously bad cutouts and
    don't care where on the tray they came from.

--fix reopens photos instantly because each run records its piece
outlines in a sidecar (<image>_pieces.json) next to the review imagery.
The sidecar also tracks which crop files a photo produced, so re-saving
replaces that photo's pieces instead of adding a second copy of each.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from flavors import flavor_for_image, slugify
from paths import ROOT

SAM_WEIGHTS = str(ROOT / "mobile_sam.pt")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")

# A "tighter" mask has to be meaningfully smaller to count as a different
# reading of the spot, rather than the same outline a few pixels in.
SHRINK_FRACTION = 0.85


# ---------------------------------------------------------------------------
# Tray localisation
# ---------------------------------------------------------------------------
def select_main_tray(candidates, frame_shape, link_frac=1.35):
    """
    Indices of the candidates sitting on the photo's main tray.

    These are display-case shots, so the flavor we want is the tray framed
    in the middle, with slices of other flavors' trays intruding at the
    edges. Identifying that tray by its own color doesn't work - the trays
    are white, but the pieces cover most of them, so the visible white
    breaks into disconnected strips, and on a dark-piece tray the biggest
    white patch can easily be a neighbour's empty border.

    The pieces themselves are a far better signal. Within one tray they're
    packed about one piece-width apart, while the gap between two trays is
    noticeably wider, so single-linkage clustering on centre distance
    separates the trays. Of the resulting groups, the wanted one has the
    most pieces and sits nearest the middle of the frame.

    Distances are judged against each pair's own piece width rather than
    one spacing for the whole photo. These trays are shot at an angle, so
    pieces at the front are both bigger and further apart in pixels than
    those at the back; a single global spacing splits one tray into a
    near half and a far half.
    """
    if len(candidates) < 3:
        return set(range(len(candidates)))

    centers = np.array([c["center"] for c in candidates], dtype=np.float32)
    distances = np.linalg.norm(centers[:, None, :] - centers[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)

    # Width of the circle with each mask's area, so "one piece apart" is
    # measured locally and survives perspective.
    widths = 1.13 * np.sqrt(np.array([c["area"] for c in candidates], dtype=np.float32))
    thresholds = link_frac * 0.5 * (widths[:, None] + widths[None, :])

    parent = list(range(len(candidates)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    linked = np.argwhere(distances < thresholds)
    for i, j in linked:
        ri, rj = find(int(i)), find(int(j))
        if ri != rj:
            parent[ri] = rj

    clusters = {}
    for i in range(len(candidates)):
        clusters.setdefault(find(i), []).append(i)

    frame_h, frame_w = frame_shape[:2]
    frame_center = np.array([frame_w / 2, frame_h / 2], dtype=np.float32)
    diagonal = float(np.hypot(frame_w, frame_h))

    best, best_score = None, -1.0
    for members in clusters.values():
        cluster_center = centers[members].mean(axis=0)
        offset = float(np.linalg.norm(cluster_center - frame_center)) / diagonal
        score = len(members) / (1.0 + 2.0 * offset)
        if score > best_score:
            best_score, best = score, members

    return set(best)


def candidate_hull(candidates, shape):
    """Convex hull over every candidate mask - a rough 'where the pieces
    are' region, used to decide where coverage-filling should prompt."""
    if not candidates:
        return None
    points = []
    for item in candidates:
        ys, xs = np.nonzero(item["mask"])
        points.append(np.stack([xs, ys], axis=1))
    hull = cv2.convexHull(np.concatenate(points).astype(np.int32))
    region = np.zeros(shape[:2], dtype=np.uint8)
    cv2.fillPoly(region, [hull], 1)
    return region.astype(bool)


# ---------------------------------------------------------------------------
# Mask geometry helpers
# ---------------------------------------------------------------------------
def largest_component(mask):
    """Drop stray islands, keeping only the biggest blob.

    SAM occasionally attaches a speck elsewhere in the frame to a mask
    (a similar highlight on another tray, usually). Left alone, that speck
    stretches the crop's bounding box across the whole photo.
    """
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8)
    if n_labels <= 2:
        return mask
    largest = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1
    return labels == largest


def mask_solidity(mask):
    """Mask area divided by its convex hull area. A dome is ~0.9+; a mask
    that grabbed two pieces plus the gap between them is much lower."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    if hull_area <= 0:
        return 0.0
    return float(area / hull_area)


def touches_border(mask, margin=2):
    return bool(mask[:margin].any() or mask[-margin:].any()
                or mask[:, :margin].any() or mask[:, -margin:].any())


# ---------------------------------------------------------------------------
# SAM passes
# ---------------------------------------------------------------------------
def seed_points_from_everything(sam_model, image, area_bounds):
    """Pass 1: every plausible fragment's centroid becomes a prompt point.

    Fragments don't need to be whole pieces - a dome-top mask and a shadow
    band both sit on the same piece, so both point at it, and duplicate
    results get merged later.
    """
    min_area, max_area = area_bounds
    result = sam_model(image, verbose=False)[0]
    if result.masks is None:
        return []

    seeds = []
    for mask in result.masks.data.cpu().numpy().astype(bool):
        area = int(mask.sum())
        if area < min_area or area > max_area:
            continue
        ys, xs = np.nonzero(mask)
        seeds.append((float(xs.mean()), float(ys.mean()), area))

    # Keep the biggest fragment in each neighbourhood; the rest of that
    # piece's fragments would only re-prompt the same object.
    typical_side = np.sqrt(np.median([s[2] for s in seeds])) if seeds else 0.0
    min_separation = 0.5 * typical_side
    kept = []
    for cx, cy, area in sorted(seeds, key=lambda s: -s[2]):
        if all(np.hypot(cx - k[0], cy - k[1]) > min_separation for k in kept):
            kept.append((cx, cy, area))
    return kept


def grid_points(shape, typical_side, spacing_frac=0.6):
    """A regular lattice of prompt points across the whole frame.

    The everything-pass misses pieces outright when it fails to fragment
    them (very glossy or very flat-lit ones), so every piece also gets
    prompted blind. Spacing below one piece width guarantees at least one
    point lands on each piece; the duplicates this creates are resolved by
    the same-object merge step.
    """
    if typical_side <= 0:
        return []

    step = max(4, int(spacing_frac * typical_side))
    height, width = shape[:2]
    return [(float(x), float(y))
            for y in range(step // 2, height, step)
            for x in range(step // 2, width, step)]


def best_mask_at_point(predictor, point, area_bounds, smaller_than=None):
    """Pass 2: prompt SAM at one point, return its largest in-range mask.

    SAM answers a point with the same object at several scales. Taking the
    largest is what you want when finding whole pieces, but `smaller_than`
    caps it, which is how the editor asks for a tighter reading of a spot
    it has already described too generously.
    """
    min_area, max_area = area_bounds
    result = predictor(points=[[float(point[0]), float(point[1])]], labels=[1])[0]
    if result.masks is None:
        return None

    best = None
    for mask in result.masks.data.cpu().numpy().astype(bool):
        mask = largest_component(mask)
        area = int(mask.sum())
        if area < min_area or area > max_area:
            continue
        if smaller_than is not None and area >= smaller_than:
            continue
        if best is None or area > best[1]:
            best = (mask, area)
    return best


def merge_candidate(candidates, mask, area):
    """Keep one mask per physical piece.

    Many prompt points land on the same piece, so a new mask either
    describes a new piece (keep it), or is a competing description of a
    piece already found - in which case the more solid, less shadow-tailed
    outline wins. A mask overlapping two or more accepted pieces is a
    merged blob spanning both, so it's discarded rather than allowed to
    swallow them.
    """
    overlapping = [i for i, other in enumerate(candidates)
                   if np.logical_and(mask, other["mask"]).sum() / min(area, other["area"]) > 0.5]

    if not overlapping:
        candidates.append(describe_mask(mask, area))
        return True
    if len(overlapping) > 1:
        return False

    incumbent = candidates[overlapping[0]]
    solidity = mask_solidity(mask)
    # Prefer the fuller outline unless it's markedly more ragged, which is
    # what a piece-plus-shadow mask looks like next to a clean piece mask.
    better = (area > incumbent["area"] and solidity > incumbent["solidity"] - 0.05) \
        or (solidity > incumbent["solidity"] + 0.05 and area > 0.6 * incumbent["area"])
    if better:
        candidates[overlapping[0]] = describe_mask(mask, area, solidity)
        return True
    return False


def describe_mask(mask, area, solidity=None):
    ys, xs = np.nonzero(mask)
    box_area = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)
    return {
        "mask": mask,
        "area": area,
        "solidity": mask_solidity(mask) if solidity is None else solidity,
        "extent": float(area / box_area),
        "center": (float(xs.mean()), float(ys.mean())),
    }


def coverage_fill_points(region, covered, typical_area):
    """Prompt points for areas inside `region` that no mask covers yet.

    This is the last chance to recover a piece both earlier rounds missed:
    if a piece-sized patch among the pieces is still bare, something is
    probably sitting there that no prompt has described yet.
    """
    if region is None:
        return []

    bare = np.logical_and(region, np.logical_not(covered)).astype(np.uint8)
    # Shrink so we don't prompt the thin gaps between already-found pieces
    erode_radius = max(3, int(0.25 * np.sqrt(typical_area)))
    bare = cv2.erode(bare, np.ones((erode_radius, erode_radius), np.uint8))

    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bare, connectivity=8)
    points = []
    for label in range(1, n_labels):
        if stats[label, cv2.CC_STAT_AREA] < 0.25 * typical_area:
            continue
        points.append((float(centroids[label][0]), float(centroids[label][1])))
    return points


# ---------------------------------------------------------------------------
# Cropping and verification imagery
# ---------------------------------------------------------------------------
def extract_rgba_crop(full_bgr, mask_small, pad_frac=0.03, feather=3):
    """Upscale a work-resolution mask back to the original photo and return
    a tight BGRA crop, so saved pieces keep full photo detail."""
    full_h, full_w = full_bgr.shape[:2]
    mask_full = cv2.resize(mask_small.astype(np.uint8) * 255, (full_w, full_h),
                           interpolation=cv2.INTER_LINEAR)

    ys, xs = np.nonzero(mask_full > 127)
    if len(xs) == 0:
        return None

    side = max(xs.max() - xs.min(), ys.max() - ys.min())
    pad = int(pad_frac * side)
    x0, x1 = max(0, xs.min() - pad), min(full_w, xs.max() + pad + 1)
    y0, y1 = max(0, ys.min() - pad), min(full_h, ys.max() + pad + 1)

    bgr = full_bgr[y0:y1, x0:x1]
    alpha = mask_full[y0:y1, x0:x1]
    if feather > 0:
        k = feather * 2 + 1
        alpha = cv2.GaussianBlur(alpha, (k, k), 0)

    return np.dstack([bgr, alpha])


def make_checkerboard(h, w, size=10):
    checker = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(0, h, size):
        for x in range(0, w, size):
            checker[y:y+size, x:x+size] = 200 if (x // size + y // size) % 2 == 0 else 150
    return checker


def flatten_rgba(rgba):
    """Composite a BGRA crop over a checkerboard so transparency is visible."""
    checker = make_checkerboard(rgba.shape[0], rgba.shape[1])
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    return (alpha * rgba[:, :, :3] + (1 - alpha) * checker).astype(np.uint8)


def build_contact_sheet(crops, cell=140, cols=8):
    """Numbered grid of every saved crop - the main thing to eyeball."""
    if not crops:
        return None

    rows = (len(crops) + cols - 1) // cols
    sheet = np.full((rows * cell, cols * cell, 3), 40, dtype=np.uint8)

    for i, rgba in enumerate(crops):
        thumb = flatten_rgba(rgba)
        h, w = thumb.shape[:2]
        scale = (cell - 12) / max(h, w)
        thumb = cv2.resize(thumb, (max(1, int(w * scale)), max(1, int(h * scale))))

        r, c = divmod(i, cols)
        y0 = r * cell + (cell - thumb.shape[0]) // 2
        x0 = c * cell + (cell - thumb.shape[1]) // 2
        sheet[y0:y0+thumb.shape[0], x0:x0+thumb.shape[1]] = thumb
        cv2.putText(sheet, str(i), (c * cell + 5, r * cell + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)

    return sheet


def build_overlay(image, accepted, rejected):
    """Original photo with accepted masks in green and rejected in red,
    each rejection labelled with the filter that dropped it."""
    overlay = image.copy()
    for item, color in ((a, (0, 255, 0)) for a in accepted):
        overlay[item["mask"]] = (0.55 * overlay[item["mask"]] + 0.45 * np.array(color)).astype(np.uint8)
    for item in rejected:
        overlay[item["mask"]] = (0.55 * overlay[item["mask"]] + 0.45 * np.array([0, 0, 255])).astype(np.uint8)

    for i, item in enumerate(accepted):
        ys, xs = np.nonzero(item["mask"])
        cv2.putText(overlay, str(i), (int(xs.mean()) - 8, int(ys.mean())),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    for item in rejected:
        ys, xs = np.nonzero(item["mask"])
        cv2.putText(overlay, item["reason"], (int(xs.min()), int(ys.mean())),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    cv2.putText(overlay, f"accepted {len(accepted)}   rejected {len(rejected)}",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    return overlay


# ---------------------------------------------------------------------------
# Saving crops, and the sidecar that makes them re-editable
# ---------------------------------------------------------------------------
def mask_polygon(mask):
    """Outline of a mask as a list of [x, y] points."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    return max(contours, key=cv2.contourArea).reshape(-1, 2).tolist()


def polygon_mask(polygon, shape):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(polygon, dtype=np.int32)], 1)
    return mask.astype(bool)


def sidecar_path(debug_dir, image_path):
    return Path(debug_dir) / f"{Path(image_path).stem}_pieces.json"


def save_pieces(full, masks, image_path, flavor, out_dir, debug_dir, cfg,
                rejected=None, work=None):
    """Write one BGRA crop per mask, plus the overlay, contact sheet and
    sidecar for this photo.

    Every crop this photo previously produced is cleared first, so editing
    a photo and re-saving replaces its pieces instead of piling a second
    copy of each one into the flavor folder. The sidecar records which
    files came from this photo, which is what makes that safe when several
    photos share one flavor folder.
    """
    class_dir = Path(out_dir) / flavor
    class_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = Path(debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    previous = read_sidecar(debug_dir, image_path)
    if previous:
        for entry in previous.get("pieces", []):
            (class_dir / entry["file"]).unlink(missing_ok=True)
        taken = set()
    else:
        # No record of this photo's own files, so don't touch anything and
        # number around whatever is already in the folder.
        taken = {p.name for p in class_dir.glob("auto_*.png")}

    entries, crops = [], []
    index = 0
    for mask in masks:
        rgba = extract_rgba_crop(full, mask, cfg.pad_frac)
        if rgba is None:
            continue
        while f"auto_{index:03d}.png" in taken:
            index += 1
        name = f"auto_{index:03d}.png"
        index += 1
        cv2.imwrite(str(class_dir / name), rgba)
        entries.append({"file": name, "polygon": mask_polygon(mask)})
        crops.append(rgba)

    if work is not None:
        accepted_items = [{"mask": m} for m in masks]
        cv2.imwrite(str(debug_dir / f"{Path(image_path).stem}_overlay.jpg"),
                    build_overlay(work, accepted_items, rejected or []))
    sheet = build_contact_sheet(crops)
    if sheet is not None:
        cv2.imwrite(str(debug_dir / f"{Path(image_path).stem}_sheet.jpg"), sheet)

    write_sidecar(debug_dir, image_path, {
        "image": str(image_path),
        "flavor": flavor,
        "out_dir": str(out_dir),
        "work_shape": list(work.shape[:2]) if work is not None else None,
        "pieces": entries,
    })
    return crops


def write_sidecar(debug_dir, image_path, payload):
    with open(sidecar_path(debug_dir, image_path), "w") as f:
        json.dump(payload, f)


def read_sidecar(debug_dir, image_path):
    path = sidecar_path(debug_dir, image_path)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Per-image pipeline
# ---------------------------------------------------------------------------
def detect_pieces(work, sam_model, predictor_factory, area_bounds, cfg):
    """Find every piece in one work-resolution photo.

    Returns (accepted, rejected) mask records; see apply_quality_gates for
    what separates the two.
    """
    seeds = seed_points_from_everything(sam_model, work, area_bounds)
    if not seeds:
        return [], []

    typical_side = float(np.sqrt(np.median([s[2] for s in seeds])))
    prompts = [(s[0], s[1]) for s in seeds] + grid_points(work.shape, typical_side, cfg.grid_spacing)

    predictor = predictor_factory()
    predictor.set_image(work)

    candidates = []
    for point in prompts:
        found = best_mask_at_point(predictor, point, area_bounds)
        if found is not None:
            merge_candidate(candidates, *found)

    covered = np.zeros(work.shape[:2], dtype=bool)
    for item in candidates:
        covered |= item["mask"]
    typical_area = float(np.median([c["area"] for c in candidates])) if candidates else 0.0
    if typical_area > 0:
        region = candidate_hull(candidates, work.shape)
        for point in coverage_fill_points(region, covered, typical_area):
            found = best_mask_at_point(predictor, point, area_bounds)
            if found is not None:
                merge_candidate(candidates, *found)
    predictor.reset_image()

    return apply_quality_gates(work, candidates, cfg)


def process_image(image_path, flavor, out_dir, debug_dir, sam_model, predictor_factory, cfg):
    full = cv2.imread(str(image_path))
    if full is None:
        print(f"  Could not read {image_path}, skipping")
        return 0

    full_h, full_w = full.shape[:2]
    scale = min(1.0, cfg.work_dim / max(full_h, full_w))
    work = cv2.resize(full, (int(full_w * scale), int(full_h * scale)))
    work_area = work.shape[0] * work.shape[1]
    area_bounds = (cfg.min_area_frac * work_area, cfg.max_area_frac * work_area)

    accepted, rejected = detect_pieces(work, sam_model, predictor_factory, area_bounds, cfg)
    if not accepted and not rejected:
        print(f"  {image_path.name}: SAM found no piece-sized regions - "
              f"try --min_area_frac lower or check the photo")
        return 0

    saved_crops = save_pieces(full, [item["mask"] for item in accepted], image_path,
                              flavor, out_dir, debug_dir, cfg,
                              rejected=rejected, work=work)

    reasons = {}
    for item in rejected:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    reason_text = ", ".join(f"{k} x{v}" for k, v in sorted(reasons.items())) or "none"
    print(f"  {image_path.name} -> {flavor}: saved {len(saved_crops)} crops "
          f"(rejected: {reason_text})")
    return len(saved_crops)


def core_color(lab, mask, area):
    """Mean Lab color of a mask's interior, ignoring its rim.

    The rim is where the piece curves away into its own shadow and where
    the mask boundary is least certain, so including it makes two
    identical pieces read as different colors depending on how much
    shadow each mask happened to pick up.
    """
    radius = max(1, int(0.15 * np.sqrt(area)))
    core = cv2.erode(mask.astype(np.uint8), np.ones((radius * 2 + 1,) * 2, np.uint8))
    if core.sum() < 0.1 * area:
        core = mask.astype(np.uint8)
    return lab[core.astype(bool)].mean(axis=0)


def apply_quality_gates(work, candidates, cfg):
    """Split candidate masks into accepted/rejected, tagging each rejection
    with the filter responsible so the overlay explains itself.

    Shape gates come first so that badly-formed masks can't distort the
    reference piece size or the tray clustering that the later gates
    measure everything against.
    """
    if not candidates:
        return [], []

    survivors, rejected = [], []
    for item in candidates:
        if touches_border(item["mask"]):
            item["reason"] = "cut off"
            rejected.append(item)
        elif item["extent"] < cfg.min_extent:
            item["reason"] = "part piece"
            rejected.append(item)
        elif item["solidity"] < cfg.min_solidity:
            item["reason"] = "ragged"
            rejected.append(item)
        else:
            survivors.append(item)

    main_tray = select_main_tray(survivors, work.shape, cfg.cluster_link)
    on_tray = []
    for i, item in enumerate(survivors):
        if i in main_tray:
            on_tray.append(item)
        else:
            item["reason"] = "other tray"
            rejected.append(item)

    if not on_tray:
        return [], rejected

    areas = np.array([c["area"] for c in on_tray], dtype=np.float32)
    median_area = float(np.median(areas))
    mad = float(np.median(np.abs(areas - median_area))) + 1e-6

    lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB).astype(np.float32)
    for item in on_tray:
        item["color"] = core_color(lab, item["mask"], item["area"])
    median_color = np.median(np.array([c["color"] for c in on_tray]), axis=0)

    accepted = []
    for item in on_tray:
        if abs(item["area"] - median_area) / (1.4826 * mad) > cfg.size_z_max:
            item["reason"] = "odd size"
            rejected.append(item)
        elif cfg.color_tol > 0 and np.linalg.norm(item["color"] - median_color) > cfg.color_tol:
            item["reason"] = "wrong color"
            rejected.append(item)
        else:
            accepted.append(item)

    return accepted, rejected


# ---------------------------------------------------------------------------
# Interactive correction, on the original photo
# ---------------------------------------------------------------------------
class MaskEditor:
    """Correct pieces by clicking the tray photo itself.

    Left-clicking a piece that is already selected drops it. Left-clicking
    anywhere else asks SAM what object is at that point and selects it, so
    a piece the automatic pass missed takes one click rather than a drawn
    box. Right-clicking two pieces in turn fuses them into one, for when a
    single chocolate came back as a dome and a separate shadow band.
    Middle-clicking asks for a smaller reading of a spot, which is how one
    mask covering two chocolates gets pulled apart.
    """

    def __init__(self, work, masks, segment_at, display_dim=900):
        self.work = work
        self.masks = list(masks)
        self.original = list(masks)
        self.segment_at = segment_at
        self.scale = min(1.0, display_dim / max(work.shape[:2]))
        self.history = []
        self.pending_merge = None
        self.status = ""
        self.dirty = True
        self.cache = None

    # -- editing ----------------------------------------------------------
    def mask_at(self, x, y):
        """Topmost selected piece under a point, or None. Most recently
        added wins, so a piece added over a stale mask is what you click."""
        for i in range(len(self.masks) - 1, -1, -1):
            if self.masks[i][y, x]:
                return i
        return None

    def click(self, x, y):
        index = self.mask_at(x, y)
        if index is not None:
            removed = self.masks.pop(index)
            self.clear_pending()
            self.history.append({"undo": "restore", "index": index, "mask": removed})
            self.status = f"removed piece {index}"
        else:
            mask = self.segment_at((x, y))
            if mask is None:
                self.status = "nothing found there - try the middle of the piece"
            else:
                self.masks.append(mask)
                self.history.append({"undo": "drop", "index": len(self.masks) - 1})
                self.status = f"added piece {len(self.masks) - 1}"
        self.dirty = True

    def tighten_click(self, x, y):
        """Middle-click: take the smaller object at this point.

        This is how one mask covering two chocolates gets separated. SAM
        describes a point at several scales, and the automatic pass keeps
        the largest reading, which is what occasionally swallows a
        neighbour. Asking for a strictly smaller one here shrinks the mask
        onto the single piece under the cursor; doing the same on the
        piece left behind recovers it as its own mask.
        """
        index = self.mask_at(x, y)
        self.clear_pending()

        if index is not None:
            current = self.masks[index]
            mask = self.segment_at((x, y), smaller_than=SHRINK_FRACTION * current.sum())
            if mask is None:
                self.status = "no smaller object here - already as tight as SAM sees it"
            else:
                self.masks[index] = mask
                self.history.append({"undo": "replace", "index": index, "mask": current})
                self.status = f"piece {index} shrunk to the piece under the cursor"
        else:
            whole = self.segment_at((x, y))
            mask = None if whole is None else self.segment_at(
                (x, y), smaller_than=SHRINK_FRACTION * whole.sum())
            mask = mask if mask is not None else whole
            if mask is None:
                self.status = "nothing found there - try the middle of the piece"
            else:
                self.masks.append(mask)
                self.history.append({"undo": "drop", "index": len(self.masks) - 1})
                self.status = f"added piece {len(self.masks) - 1} (tight)"
        self.dirty = True

    def merge_click(self, x, y):
        """Right-click: pick a piece, then pick the one to fuse it with."""
        index = self.mask_at(x, y)
        if index is None:
            self.status = "right-click a piece to start a merge"
        elif self.pending_merge is None:
            self.pending_merge = index
            self.status = f"merging piece {index} - right-click the other half"
        elif self.pending_merge == index:
            self.clear_pending()
            self.status = "merge cancelled"
        else:
            self.merge(self.pending_merge, index)
        self.dirty = True

    def merge(self, i, j):
        """Fuse two masks into one piece.

        A straight union, plus a small closing to seal the hairline seam
        where the two outlines meet, so the result reads as one solid
        piece instead of two touching ones with a crack between them.
        """
        first, second = sorted((i, j))
        parts = [(first, self.masks[first]), (second, self.masks[second])]

        union = np.logical_or(parts[0][1], parts[1][1])
        radius = max(3, int(0.03 * np.sqrt(union.sum())))
        union = cv2.morphologyEx(union.astype(np.uint8), cv2.MORPH_CLOSE,
                                 np.ones((radius, radius), np.uint8)).astype(bool)

        self.masks.pop(second)
        self.masks.pop(first)
        self.masks.append(union)
        self.clear_pending()
        self.history.append({"undo": "split", "index": len(self.masks) - 1, "parts": parts})
        self.status = f"merged pieces {first} and {second}"

    def clear_pending(self):
        self.pending_merge = None

    def undo(self):
        if not self.history:
            self.status = "nothing to undo"
            self.dirty = True
            return

        action = self.history.pop()
        self.clear_pending()
        if action["undo"] == "restore":
            self.masks.insert(action["index"], action["mask"])
            self.status = "undo: restored a piece"
        elif action["undo"] == "drop":
            self.masks.pop(action["index"])
            self.status = "undo: removed the added piece"
        elif action["undo"] == "replace":
            self.masks[action["index"]] = action["mask"]
            self.status = "undo: back to the wider mask"
        else:
            self.masks.pop(action["index"])
            for index, mask in action["parts"]:
                self.masks.insert(index, mask)
            self.status = "undo: split the merged piece"
        self.dirty = True

    def reset(self):
        self.masks = list(self.original)
        self.history.clear()
        self.clear_pending()
        self.status = "reset to the automatic result"
        self.dirty = True

    def on_mouse(self, event, x, y, flags, param):
        if event not in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN, cv2.EVENT_MBUTTONDOWN):
            return
        wx, wy = int(x / self.scale), int(y / self.scale)
        h, w = self.work.shape[:2]
        if not (0 <= wx < w and 0 <= wy < h):
            return

        if event == cv2.EVENT_RBUTTONDOWN:
            self.merge_click(wx, wy)
        elif event == cv2.EVENT_MBUTTONDOWN or flags & cv2.EVENT_FLAG_SHIFTKEY:
            # shift+left-click does the same, for mice without a middle button
            self.tighten_click(wx, wy)
        else:
            self.click(wx, wy)

    # -- drawing ----------------------------------------------------------
    def render(self):
        if self.dirty or self.cache is None:
            overlay = self.work.copy()
            for i, mask in enumerate(self.masks):
                tint = (0, 200, 255) if i == self.pending_merge else (0, 255, 0)
                overlay[mask] = (0.55 * overlay[mask] + 0.45 * np.array(tint)).astype(np.uint8)
                contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(overlay, contours, -1, (255, 255, 255), 1)
                ys, xs = np.nonzero(mask)
                cv2.putText(overlay, str(i), (int(xs.mean()) - 8, int(ys.mean())),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            if self.scale < 1.0:
                overlay = cv2.resize(overlay, (int(overlay.shape[1] * self.scale),
                                               int(overlay.shape[0] * self.scale)))
            self.cache = overlay
            self.dirty = False

        canvas = self.cache.copy()
        cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 52), (0, 0, 0), -1)
        cv2.putText(canvas, f"pieces: {len(self.masks)}    {self.status}",
                    (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
        cv2.putText(canvas, "[L-click: remove / add] [R-click x2: merge] "
                            "[M-click or shift+click: split off one piece] "
                            "[u undo] [r reset] [s save] [n skip] [q quit]",
                    (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
        return canvas

    def run(self, title):
        """Returns 'save', 'skip' or 'quit'."""
        window = f"Fix pieces - {title}"
        cv2.namedWindow(window)
        cv2.setMouseCallback(window, self.on_mouse)
        try:
            while True:
                cv2.imshow(window, self.render())
                key = cv2.waitKey(20) & 0xFF
                if key == ord('s'):
                    return "save"
                if key == ord('n'):
                    return "skip"
                if key == ord('q'):
                    return "quit"
                if key == ord('u'):
                    self.undo()
                elif key == ord('r'):
                    self.reset()
        finally:
            cv2.destroyWindow(window)


def fix_images(image_paths, out_dir, debug_dir, cfg):
    """Walk photos, letting you correct each one's pieces by clicking.

    Masks are rebuilt from each photo's sidecar so this starts instantly;
    a photo that was never extracted (or whose sidecar is gone) is
    segmented from scratch first.
    """
    from ultralytics import SAM
    from ultralytics.models.sam import Predictor as SAMPredictor

    sam_model, predictor = None, None

    def predictor_factory():
        return SAMPredictor(overrides=dict(task="segment", mode="predict",
                                           model=SAM_WEIGHTS, imgsz=cfg.work_dim,
                                           save=False, verbose=False))

    for image_path in image_paths:
        image_path = Path(image_path)
        record = read_sidecar(debug_dir, image_path)
        full = cv2.imread(str(image_path))
        if full is None:
            print(f"  Could not read {image_path}, skipping")
            continue

        full_h, full_w = full.shape[:2]
        scale = min(1.0, cfg.work_dim / max(full_h, full_w))
        work = cv2.resize(full, (int(full_w * scale), int(full_h * scale)))
        work_area = work.shape[0] * work.shape[1]
        area_bounds = (cfg.min_area_frac * work_area, cfg.max_area_frac * work_area)

        if record:
            flavor = record["flavor"]
            masks = [polygon_mask(p["polygon"], work.shape) for p in record["pieces"]
                     if p["polygon"]]
        else:
            flavor = slugify(cfg.flavor) if cfg.flavor else flavor_for_image(image_path)
            print(f"  {image_path.name}: no saved pieces, segmenting first "
                  f"(about 15s)...")
            if sam_model is None:
                sam_model = SAM(SAM_WEIGHTS)
            masks = [item["mask"] for item in
                     detect_pieces(work, sam_model, predictor_factory, area_bounds, cfg)[0]]

        if predictor is None:
            predictor = predictor_factory()
        predictor.set_image(work)

        def segment_at(point, smaller_than=None):
            found = best_mask_at_point(predictor, point, area_bounds, smaller_than)
            if found is None:
                # The click was explicit, so trust it over the size window
                # that the automatic pass uses to stay conservative.
                found = best_mask_at_point(predictor, point,
                                           (0.2 * area_bounds[0], 3.0 * area_bounds[1]),
                                           smaller_than)
            return None if found is None else found[0]

        editor = MaskEditor(work, masks, segment_at, cfg.display_dim)
        action = editor.run(f"{image_path.name} ({flavor})")
        predictor.reset_image()

        if action == "save":
            crops = save_pieces(full, editor.masks, image_path, flavor,
                                out_dir, debug_dir, cfg, work=work)
            print(f"  {image_path.name} -> {flavor}: {len(crops)} pieces saved")
        elif action == "quit":
            print("  stopped")
            break
        else:
            print(f"  {image_path.name}: skipped, nothing changed")


# ---------------------------------------------------------------------------
# Interactive verification
# ---------------------------------------------------------------------------
class CropReviewer:
    """Click a thumbnail to mark it for deletion, then commit with 'd'."""

    def __init__(self, paths, cell=160, cols=8, rows=5):
        self.paths = paths
        self.cell, self.cols, self.rows = cell, cols, rows
        self.per_page = cols * rows
        self.page = 0
        self.rejected = set()
        self.thumbs = {}

    def page_paths(self):
        start = self.page * self.per_page
        return self.paths[start:start + self.per_page]

    def thumb(self, path):
        if path not in self.thumbs:
            rgba = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if rgba is None:
                self.thumbs[path] = np.zeros((self.cell, self.cell, 3), dtype=np.uint8)
            else:
                if rgba.shape[2] == 4:
                    rgba = flatten_rgba(rgba)
                h, w = rgba.shape[:2]
                scale = (self.cell - 12) / max(h, w)
                self.thumbs[path] = cv2.resize(rgba, (max(1, int(w * scale)),
                                                      max(1, int(h * scale))))
        return self.thumbs[path]

    def on_mouse(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        col, row = x // self.cell, (y - 40) // self.cell
        if row < 0 or col >= self.cols or row >= self.rows:
            return
        index = row * self.cols + col
        page = self.page_paths()
        if index >= len(page):
            return
        path = page[index]
        self.rejected.symmetric_difference_update({path})

    def render(self):
        canvas = np.full((self.rows * self.cell + 40, self.cols * self.cell, 3), 40, dtype=np.uint8)
        page = self.page_paths()
        n_pages = max(1, (len(self.paths) + self.per_page - 1) // self.per_page)

        for i, path in enumerate(page):
            thumb = self.thumb(path)
            r, c = divmod(i, self.cols)
            y0 = 40 + r * self.cell + (self.cell - thumb.shape[0]) // 2
            x0 = c * self.cell + (self.cell - thumb.shape[1]) // 2
            canvas[y0:y0+thumb.shape[0], x0:x0+thumb.shape[1]] = thumb

            if path in self.rejected:
                cv2.rectangle(canvas, (c * self.cell + 2, 40 + r * self.cell + 2),
                              ((c + 1) * self.cell - 2, 40 + (r + 1) * self.cell - 2),
                              (0, 0, 255), 3)
                cv2.line(canvas, (c * self.cell + 8, 40 + r * self.cell + 8),
                         ((c + 1) * self.cell - 8, 40 + (r + 1) * self.cell - 8), (0, 0, 255), 2)

        cv2.putText(canvas, f"{self.paths[0].parent.name}  page {self.page+1}/{n_pages}  "
                            f"marked {len(self.rejected)}  "
                            f"[click=toggle] [n/p page] [d delete marked] [q done]",
                    (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        return canvas

    def run(self):
        window = "Review crops"
        cv2.namedWindow(window)
        cv2.setMouseCallback(window, self.on_mouse)
        n_pages = max(1, (len(self.paths) + self.per_page - 1) // self.per_page)

        while True:
            cv2.imshow(window, self.render())
            key = cv2.waitKey(20) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('n'):
                self.page = min(self.page + 1, n_pages - 1)
            elif key == ord('p'):
                self.page = max(self.page - 1, 0)
            elif key == ord('d') and self.rejected:
                for path in self.rejected:
                    Path(path).unlink(missing_ok=True)
                print(f"  deleted {len(self.rejected)} crops")
                self.paths = [p for p in self.paths if p not in self.rejected]
                self.rejected.clear()
                if not self.paths:
                    break
                n_pages = max(1, (len(self.paths) + self.per_page - 1) // self.per_page)
                self.page = min(self.page, n_pages - 1)

        cv2.destroyWindow(window)


def review(out_dir):
    out_dir = Path(out_dir)
    class_dirs = sorted(d for d in out_dir.iterdir() if d.is_dir() and not d.name.startswith("_"))
    if not class_dirs:
        raise SystemExit(f"No flavor folders in '{out_dir}' yet - run the extraction first.")

    for class_dir in class_dirs:
        paths = sorted(class_dir.glob("auto_*.png"))
        if not paths:
            continue
        print(f"Reviewing '{class_dir.name}' ({len(paths)} crops)")
        CropReviewer(paths).run()

    print("\nReview done.")


def selected_images(args, debug_dir):
    """Which photos to work on: whatever was asked for explicitly, or for
    --fix, every photo already extracted (found via its sidecar)."""
    if args.image:
        return [Path(args.image)]

    if args.image_dir:
        image_dir = Path(args.image_dir)
        if not image_dir.exists():
            raise SystemExit(f"'{image_dir}' does not exist")
        paths = sorted(p for p in image_dir.glob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
        if not paths:
            raise SystemExit(f"No images found in '{image_dir}'")
        return paths

    records = sorted(Path(debug_dir).glob("*_pieces.json"))
    if not records:
        raise SystemExit(f"No extracted photos found in '{debug_dir}'. Run the "
                         f"extraction first, or pass --image / --image_dir.")
    return [Path(json.loads(p.read_text())["image"]) for p in records]


# ---------------------------------------------------------------------------
def main():
    from paths import use_repo_root
    use_repo_root()
    parser = argparse.ArgumentParser(description="Automated SAM-based piece extraction from tray photos")
    parser.add_argument("--image", help="Single image to process")
    parser.add_argument("--image_dir", help="Folder of tray photos to process")
    parser.add_argument("--flavor", help="Override flavor from labels.json")
    parser.add_argument("--out_dir", default="automated_raw_pieces")
    parser.add_argument("--debug_dir",
                        help="Where verification images go (default: <out_dir>_review)")
    parser.add_argument("--review", action="store_true",
                        help="Skip extraction; visually review and delete bad crops")
    parser.add_argument("--fix", action="store_true",
                        help="Skip extraction; correct pieces by clicking the tray photo - "
                             "click a piece to drop it, click an unselected one to add it")
    parser.add_argument("--display_dim", type=int, default=900,
                        help="Window size for --fix, as the photo's long side")

    parser.add_argument("--work_dim", type=int, default=1024,
                        help="Long side used for segmentation (crops stay full-res)")
    parser.add_argument("--min_area_frac", type=float, default=0.0015,
                        help="Smallest plausible piece, as a fraction of the frame")
    parser.add_argument("--max_area_frac", type=float, default=0.06,
                        help="Largest plausible piece, as a fraction of the frame")
    parser.add_argument("--cluster_link", type=float, default=1.35,
                        help="Tray-splitting distance, as a multiple of piece spacing")
    parser.add_argument("--size_z_max", type=float, default=3.5,
                        help="Max robust z-score of piece area before it's an outlier")
    parser.add_argument("--min_solidity", type=float, default=0.80,
                        help="Min mask area / convex hull area")
    parser.add_argument("--min_extent", type=float, default=0.58,
                        help="Min mask area / bounding box area; a whole piece fills "
                             "about 0.7 of its box, half a piece much less")
    parser.add_argument("--grid_spacing", type=float, default=0.6,
                        help="Blind prompt lattice spacing, as a fraction of piece width")
    parser.add_argument("--color_tol", type=float, default=45.0,
                        help="Max Lab distance from the tray's median piece color (0 disables)")
    parser.add_argument("--pad_frac", type=float, default=0.03,
                        help="Padding around each crop, as a fraction of piece size")
    args = parser.parse_args()
    debug_dir = args.debug_dir or f"{args.out_dir.rstrip('/').rstrip(chr(92))}_review"

    if args.review:
        review(args.out_dir)
        return

    if args.fix:
        fix_images(selected_images(args, debug_dir), args.out_dir, debug_dir, args)
        print("\nFixing done.")
        return

    if not args.image and not args.image_dir:
        raise SystemExit("Provide --image <file>, --image_dir <folder>, --review, or --fix")

    image_paths = selected_images(args, debug_dir)

    # Imported here so --review works without loading torch
    from ultralytics import SAM
    from ultralytics.models.sam import Predictor as SAMPredictor

    print(f"Loading SAM ('{SAM_WEIGHTS}', downloads once then runs offline)...")
    sam_model = SAM(SAM_WEIGHTS)

    def predictor_factory():
        return SAMPredictor(overrides=dict(task="segment", mode="predict",
                                           model=SAM_WEIGHTS, imgsz=args.work_dim,
                                           save=False, verbose=False))

    print(f"Processing {len(image_paths)} image(s) -> '{args.out_dir}/'")
    total = 0
    for image_path in image_paths:
        flavor = slugify(args.flavor) if args.flavor else flavor_for_image(image_path)
        total += process_image(image_path, flavor, args.out_dir, debug_dir,
                               sam_model, predictor_factory, args)

    print(f"\nDone. {total} crops saved to '{args.out_dir}/'")
    print(f"VERIFY BEFORE USING: open '{debug_dir}/*_overlay.jpg' to see what was "
          f"accepted (green) vs rejected (red), and '*_sheet.jpg' for the saved crops.")
    print(f"Then run:  python pipeline/auto_crop_pieces.py --review   to click away any bad ones.")


if __name__ == "__main__":
    main()
