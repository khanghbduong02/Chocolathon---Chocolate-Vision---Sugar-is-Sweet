"""
Drag-to-Crop: Manually Mark Piece Bounding Boxes on Real Tray Photos
=========================================================================

WHY THIS EXISTS
----------------
On real shop tray photos, pieces are often packed edge-to-edge with the
same color and almost no visible gap - automated segmentation (color
thresholding, watershed, Hough circles, perspective-grid slicing) all
struggle here because there just isn't enough visual signal to split on.

A human eye separates them instantly, though. So instead of fighting
automated detection, this tool lets you drag a box around each piece.

Pieces also aren't all the same size in these photos - ones closer to
the camera appear larger than ones farther back, due to perspective.
A fixed-size click-to-center box can't capture that, so this version
uses a real click-drag-release rectangle per piece: you draw a box that
actually matches that piece's size and position, near or far.

CONTROLS
--------
- Crosshair guide lines follow the cursor to help line up box edges
- Left click + drag + release: draw a bounding box around one piece
- 'u': undo the last box
- 's': save all boxes for this image and move to the next one
- 'q': quit without saving the current image

USAGE
-----
Single image:
    python pipeline/click_to_crop.py --image tray_photos/confetti_cake.jpg

Folder of images, flavor taken from labels.json:
    python pipeline/click_to_crop.py --image_dir tray_photos/

OUTPUT
------
raw_pieces/<flavor>/click_000.png, click_001.png, ...

These are plain crops (no alpha channel / background removal) - since
they came from real photos with real backgrounds, they get pasted onto
synthetic backgrounds as opaque rectangles rather than alpha-blended
cutouts. This is a reasonable tradeoff for speed; if you want cleaner
cutouts, you could pipe these through a background-removal pass
afterward.
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from flavors import flavor_for_image, slugify


class DragCropper:
    def __init__(self, display_image, scale):
        self.display_image = display_image  # resized-for-display image
        self.scale = scale  # display_size = original_size * scale
        self.boxes = []  # list of (x0, y0, x1, y1) in ORIGINAL image coordinates
        self.dragging = False
        self.drag_start = None  # in display coordinates
        self.drag_current = None  # in display coordinates
        self.cursor = None  # last known cursor position, in display coordinates

    def on_mouse(self, event, x, y, flags, param):
        self.cursor = (x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            self.dragging = True
            self.drag_start = (x, y)
            self.drag_current = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.dragging:
            self.drag_current = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self.dragging:
            self.dragging = False
            x0d, y0d = self.drag_start
            x1d, y1d = (x, y)
            # ignore accidental tiny clicks (no real drag)
            if abs(x1d - x0d) < 5 or abs(y1d - y0d) < 5:
                self.drag_start = None
                self.drag_current = None
                return
            # convert display coords -> original image coords
            ox0, oy0 = int(min(x0d, x1d) / self.scale), int(min(y0d, y1d) / self.scale)
            ox1, oy1 = int(max(x0d, x1d) / self.scale), int(max(y0d, y1d) / self.scale)
            self.boxes.append((ox0, oy0, ox1, oy1))
            self.drag_start = None
            self.drag_current = None

    def draw_crosshair(self, disp):
        """Full-width/height guide lines through the cursor, so box edges can be
        lined up with pieces elsewhere in the tray before starting the drag."""
        if self.cursor is None:
            return
        h, w = disp.shape[:2]
        cx, cy = self.cursor
        # dark underlay first so the bright line stays readable on light photos
        cv2.line(disp, (0, cy), (w, cy), (0, 0, 0), 3)
        cv2.line(disp, (cx, 0), (cx, h), (0, 0, 0), 3)
        cv2.line(disp, (0, cy), (w, cy), (255, 0, 255), 1)
        cv2.line(disp, (cx, 0), (cx, h), (255, 0, 255), 1)

    def render(self):
        disp = self.display_image.copy()
        for (ox0, oy0, ox1, oy1) in self.boxes:
            dx0, dy0 = int(ox0 * self.scale), int(oy0 * self.scale)
            dx1, dy1 = int(ox1 * self.scale), int(oy1 * self.scale)
            cv2.rectangle(disp, (dx0, dy0), (dx1, dy1), (0, 255, 0), 2)
        self.draw_crosshair(disp)
        if self.dragging and self.drag_start and self.drag_current:
            cv2.rectangle(disp, self.drag_start, self.drag_current, (0, 255, 255), 2)
        cv2.putText(disp, f"Boxes: {len(self.boxes)}  "
                          f"[drag to draw] [u undo] [s save+next] [q quit]",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        return disp


def run_on_image(image_path, flavor, out_dir, max_display_dim=900):
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"  Could not read {image_path}, skipping")
        return 0

    h, w = img.shape[:2]
    scale = min(1.0, max_display_dim / max(h, w))
    display_size = (int(w * scale), int(h * scale))
    display_image = cv2.resize(img, display_size)

    cropper = DragCropper(display_image, scale)

    window_name = f"Drag a box around each piece - {image_path.name} (flavor: {flavor})"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, cropper.on_mouse)

    while True:
        cv2.imshow(window_name, cropper.render())
        key = cv2.waitKey(20) & 0xFF
        if key == ord('s'):
            break
        elif key == ord('q'):
            cv2.destroyWindow(window_name)
            return 0
        elif key == ord('u') and cropper.boxes:
            cropper.boxes.pop()

    cv2.destroyWindow(window_name)

    class_dir = Path(out_dir) / flavor
    class_dir.mkdir(parents=True, exist_ok=True)
    existing = len(list(class_dir.glob("click_*.png")))
    saved = 0
    for i, (x0, y0, x1, y1) in enumerate(cropper.boxes):
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        cv2.imwrite(str(class_dir / f"click_{existing+saved:03d}.png"), crop)
        saved += 1

    print(f"  {image_path.name}: saved {saved} crops to {class_dir}/")
    return saved


def main():
    from paths import use_repo_root
    use_repo_root()
    parser = argparse.ArgumentParser(description="Drag-to-crop piece extraction from tray photos")
    parser.add_argument("--image", help="Single image to process")
    parser.add_argument("--image_dir", help="Folder of images to process")
    parser.add_argument("--flavor", help="Flavor name for all images (default: labels.json)")
    parser.add_argument("--prompt_per_image", action="store_true",
                         help="Ask for a flavor name for each image individually")
    parser.add_argument("--out_dir", default="raw_pieces")
    args = parser.parse_args()

    if not args.image and not args.image_dir:
        raise SystemExit("Provide --image <file> or --image_dir <folder>")

    if args.image:
        image_paths = [Path(args.image)]
    else:
        image_dir = Path(args.image_dir)
        if not image_dir.exists():
            image_dir.mkdir(parents=True, exist_ok=True)
            raise SystemExit(f"'{image_dir}' didn't exist, so I created it - "
                              f"add tray photos to it and run this again.")
        image_paths = sorted([p for p in image_dir.glob("*")
                               if p.suffix.lower() in [".jpg", ".jpeg", ".png"]])
        if not image_paths:
            raise SystemExit(f"No images found in '{image_dir}'")

    total = 0
    for image_path in image_paths:
        flavor = slugify(args.flavor) if args.flavor else flavor_for_image(image_path)
        if args.prompt_per_image:
            default_flavor = flavor
            flavor = input(f"Flavor name for '{image_path.name}' "
                            f"[Enter for {default_flavor}, 'skip' to skip]: ").strip()
            if flavor.lower() == "skip":
                continue
            flavor = slugify(flavor or default_flavor)

        total += run_on_image(image_path, flavor, args.out_dir)

    print(f"\nDone. {total} piece crops saved across all images.")


if __name__ == "__main__":
    main()