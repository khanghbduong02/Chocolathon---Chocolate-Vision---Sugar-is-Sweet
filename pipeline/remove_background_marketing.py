"""
Remove Backgrounds from Marketing / Studio Chocolate Photos
==============================================================

WHY THIS IS A DIFFERENT SCRIPT FROM auto_crop_pieces.py
------------------------------------------------------------
Tray photos have many pieces on a white insert, so SAM finds each one.

Marketing photos are a different beast: studio lighting, soft shadows
under the chocolate, sometimes a reflective surface, occasional props
(a mint leaf, a dusting of cocoa powder, a plate edge). Simple
thresholding tends to eat into shadows or leave halos. So this script
uses a real salient-object segmentation model (via the `rembg` library,
which runs a small pretrained network - u2net - fully offline after the
one-time model download) instead of a hand-rolled color threshold.

FOLDER STRUCTURE EXPECTED
--------------------------
marketing_images/
    confetti_cake.webp
    caramel_apple_cider.webp
    ...
(one photo per flavor, filename = flavor slug from labels.json)

OUTPUT
------
automated_raw_pieces/
    confetti_cake/
        marketing_000.png    <- background removed, alpha channel = mask
    caramel_apple_cider/
        marketing_000.png
    ...

This writes into the SAME automated_raw_pieces/ folder used by
auto_crop_pieces.py, using a `marketing_` filename prefix so tray crops
and marketing crops sit side by side without colliding.

IMPORTANT CAVEATS (read before trusting this data heavily)
-------------------------------------------------------------
- One marketing photo per flavor means ONE viewing angle, One lighting
  setup, one specific piece's exact shape/imperfections. This gives you
  a "what should this generally look like" reference, not real
  within-flavor variation the way 20+ plate photos of the same flavor do.
- If the marketing photo is angled (not top-down) or has visible steam/
  garnish/a bite taken out (common in food photography), the cutout will
  include that - inspect the debug output for each flavor before trusting it.
- Treat this as a SECONDARY data source that adds a bit of extra visual
  variety, not a replacement for your own plate photos as the primary
  training signal.

USAGE
-----
    python pipeline/remove_background_marketing.py

Then check automated_raw_pieces/<flavor>/marketing_000_debug.jpg for each flavor to
confirm the cutout looks clean (no background halo, no missing chunk of
the piece) before using it in the compositing step.
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
from rembg import remove, new_session

from flavors import flavor_for_image, match_marketing_stem


def tight_crop(rgba: np.ndarray, pad: int = 6):
    """Crop to the tight bounding box of non-transparent pixels."""
    alpha = rgba[:, :, 3]
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        return None
    h, w = alpha.shape
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad)
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad)
    return rgba[y0:y1, x0:x1]


def clean_mask(rgba: np.ndarray, min_area_frac: float = 0.02):
    """
    rembg sometimes leaves small stray islands (shadow flecks, prop
    fragments). Keep only the largest connected alpha region so we get
    one clean piece, not the piece plus debris.
    """
    alpha = rgba[:, :, 3]
    _, binary = cv2.threshold(alpha, 20, 255, cv2.THRESH_BINARY)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    if n_labels <= 1:
        return rgba  # nothing found, leave as-is (will get filtered later)

    # stats[0] is background; find the largest real component
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest_idx = np.argmax(areas) + 1
    total_area = binary.shape[0] * binary.shape[1]

    if stats[largest_idx, cv2.CC_STAT_AREA] < min_area_frac * total_area:
        return None  # nothing substantial found - likely a bad removal

    clean = np.zeros_like(alpha)
    clean[labels == largest_idx] = alpha[labels == largest_idx]
    rgba = rgba.copy()
    rgba[:, :, 3] = clean
    return rgba


def process_image(img_path: Path, session, out_dir: Path, debug: bool = True):
    with open(img_path, "rb") as f:
        input_bytes = f.read()

    output_bytes = remove(input_bytes, session=session)
    arr = np.frombuffer(output_bytes, dtype=np.uint8)
    rgba = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)

    if rgba is None or rgba.shape[2] != 4:
        print(f"  Failed to process {img_path.name} - unexpected output format")
        return False

    rgba = clean_mask(rgba)
    if rgba is None:
        print(f"  {img_path.name}: background removal found nothing substantial - "
              f"check the source photo, or try again (lighting/contrast may be too low)")
        return False

    cropped = tight_crop(rgba)
    if cropped is None:
        print(f"  {img_path.name}: crop failed after masking")
        return False

    out_path = out_dir / "marketing_000.png"
    cv2.imwrite(str(out_path), cropped)

    if debug:
        # Small side-by-side: original vs. cutout on a checkerboard,
        # so transparency is visible
        checker = make_checkerboard(cropped.shape[0], cropped.shape[1])
        alpha = cropped[:, :, 3:4].astype(np.float32) / 255.0
        composited = (alpha * cropped[:, :, :3] + (1 - alpha) * checker).astype(np.uint8)
        cv2.imwrite(str(out_dir / "marketing_000_debug.jpg"), composited)

    return True


def make_checkerboard(h, w, size=10):
    checker = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(0, h, size):
        for x in range(0, w, size):
            if (x // size + y // size) % 2 == 0:
                checker[y:y+size, x:x+size] = 200
            else:
                checker[y:y+size, x:x+size] = 150
    return checker


def main():
    from paths import use_repo_root
    use_repo_root()
    parser = argparse.ArgumentParser(description="Remove backgrounds from marketing chocolate photos")
    parser.add_argument("--marketing_dir", default="marketing_images")
    parser.add_argument("--out_dir", default="automated_raw_pieces")
    args = parser.parse_args()

    marketing_dir = Path(args.marketing_dir)
    if not marketing_dir.exists():
        marketing_dir.mkdir(parents=True, exist_ok=True)
        raise SystemExit(f"'{marketing_dir}' didn't exist, so I created it - but it's empty. "
                          f"Save one photo per flavor into '{marketing_dir}/' and run this again.")

    image_paths = sorted([p for p in marketing_dir.iterdir()
                           if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]])
    if not image_paths:
        raise SystemExit(f"'{marketing_dir}' exists but has no .jpg/.jpeg/.png/.webp files in it. "
                          f"Add flavor photos and run this again.")

    print(f"Found {len(image_paths)} marketing images. Loading segmentation model "
          f"(downloads once, then runs fully offline)...")
    session = new_session("u2net")

    succeeded, failed = 0, []
    for img_path in image_paths:
        flavor_name = match_marketing_stem(img_path.stem) or flavor_for_image(img_path)
        out_dir = Path(args.out_dir) / flavor_name
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"Processing '{img_path.name}' -> class '{flavor_name}'")
        ok = process_image(img_path, session, out_dir)
        if ok:
            succeeded += 1
        else:
            failed.append(img_path.name)

    print(f"\nDone. {succeeded}/{len(image_paths)} processed successfully.")
    if failed:
        print(f"Failed or low-confidence: {failed}")
        print("Check these manually - low contrast between chocolate and background, "
              "or a very busy/cluttered photo, are the usual causes.")
    print(f"\nCheck automated_raw_pieces/<flavor>/marketing_000_debug.jpg for each flavor "
          f"before using this data - verify the cutout doesn't include background "
          f"halo or clip off part of the piece.")


if __name__ == "__main__":
    main()