"""
Find the real cavity grid of a chocolate box insert
=====================================================

The empty-box photos are taken by hand, so the insert is never square-on
in the frame: it is a quadrilateral, the far row is smaller than the near
row, and the lip around the cavities is a different width on every box.
Laying an even grid over the insert's bounding box therefore puts a lot
of the slots on walls instead of in cavities.

This module does it the other way round:

1. `detect_insert_quad` finds the gold rim and takes the hole inside it.
   The rim is the one thing every photo has, and it is a closed ring, so
   its inner contour is the insert outline - corners included.
2. `rectify` warps that quadrilateral to a flat rectangle, which undoes
   the perspective. Cavities become an axis-aligned lattice.
3. `fit_axis` locks a (start, pitch) pair onto that lattice from the
   brightness profile: cavity floors catch the light, the walls between
   them stay dark, so the profile is a square wave with `cols` (or
   `rows`) periods. A brute-force search over start and pitch beats
   blob-finding here because the floors often merge into one blob.

`detect_tray` ties the three together and hands back a `TrayLayout` that
can map cell centres both ways, so a caller can composite pieces in the
flat rectified view and warp the result back onto the original photo.
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class TrayLayout:
    """Where the cavities are, in both the photo and a flattened view.

    `H` maps photo -> rectified. `cells` are (cx, cy, w, h) in rectified
    pixels; use `cells_in_photo()` for the same slots in photo pixels.
    """
    quad: np.ndarray
    H: np.ndarray
    size: tuple
    cells: list
    rows: int
    cols: int
    score: float

    @property
    def H_inv(self):
        return np.linalg.inv(self.H)

    def cells_in_photo(self):
        """Cavities as (cx, cy, w, h) in photo pixels.

        The width and height come from mapping the cell's own corners,
        not from one global scale, so a cavity at the back of a tilted
        tray correctly comes out smaller than one at the front.
        """
        inverse = self.H_inv
        corners = np.array([[[cx - cw / 2, cy - ch / 2], [cx + cw / 2, cy - ch / 2],
                             [cx + cw / 2, cy + ch / 2], [cx - cw / 2, cy + ch / 2],
                             [cx, cy]] for cx, cy, cw, ch in self.cells], np.float32)
        mapped = cv2.perspectiveTransform(corners.reshape(1, -1, 2), inverse)[0]
        mapped = mapped.reshape(-1, 5, 2)
        widths = np.linalg.norm(mapped[:, 1] - mapped[:, 0], axis=1)
        heights = np.linalg.norm(mapped[:, 3] - mapped[:, 0], axis=1)
        return [(float(c[4][0]), float(c[4][1]), float(w), float(h))
                for c, w, h in zip(mapped, widths, heights)]


def order_quad(points):
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    diag = pts.sum(1)
    anti = pts[:, 0] - pts[:, 1]
    return np.array([pts[np.argmin(diag)], pts[np.argmax(anti)],
                     pts[np.argmax(diag)], pts[np.argmin(anti)]], dtype=np.float32)


def contour_to_quad(contour):
    peri = cv2.arcLength(contour, True)
    for frac in np.arange(0.01, 0.12, 0.004):
        approx = cv2.approxPolyDP(contour, frac * peri, True)
        if len(approx) == 4:
            return order_quad(approx)
    return order_quad(cv2.boxPoints(cv2.minAreaRect(contour)))


def detect_insert_quad(bgr):
    """Corners of the black insert, as TL, TR, BR, BL in pixel coords.

    Found as the hole inside the gold rim rather than by segmenting the
    insert directly - the insert is the same near-black as the open lid
    and most of these display cases, but nothing else in frame is a big
    gold ring.
    """
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    gold = cv2.inRange(hsv, (8, 35, 70), (42, 255, 255))
    k = max(5, int(0.006 * max(h, w)) | 1)
    gold = cv2.morphologyEx(gold, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    gold = cv2.morphologyEx(gold, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    contours, hierarchy = cv2.findContours(gold, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return None
    hierarchy = hierarchy[0]
    best, best_area = None, -1.0
    for i, contour in enumerate(contours):
        if hierarchy[i][3] != -1 or cv2.contourArea(contour) < 0.01 * h * w:
            continue
        child = hierarchy[i][2]
        while child != -1:
            area = cv2.contourArea(contours[child])
            _, y, _, bh = cv2.boundingRect(contours[child])
            if area > 0.02 * h * w and y + bh / 2 > 0.3 * h and area > best_area:
                best_area, best = area, contours[child]
            child = hierarchy[child][0]
    if best is None:
        return None
    return contour_to_quad(best)


def rectify_matrix(quad, long_side=900, pad_frac=0.10):
    """Homography photo -> flattened insert, plus the canvas size.

    A margin of `pad_frac` is kept around the insert so a cavity row that
    the rim contour clipped short still has somewhere to live.
    """
    tl, tr, br, bl = quad
    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    scale = long_side / max(width, height)
    inner_w, inner_h = width * scale, height * scale
    pad = pad_frac * min(inner_w, inner_h)
    canvas = (int(round(inner_w + 2 * pad)), int(round(inner_h + 2 * pad)))
    dst = np.array([[pad, pad], [pad + inner_w, pad],
                    [pad + inner_w, pad + inner_h], [pad, pad + inner_h]], np.float32)
    return cv2.getPerspectiveTransform(quad.astype(np.float32), dst), canvas


def rectify(bgr, quad, long_side=900, pad_frac=0.10):
    """Flatten the insert. Returns (warp, H) where H maps photo -> warp."""
    H, canvas = rectify_matrix(quad, long_side, pad_frac)
    return cv2.warpPerspective(bgr, H, canvas), H


def lattice_profiles(warp, inner):
    """Brightness and wall-edge profiles of the insert interior.

    CLAHE first: on the matte-black inserts the wall/floor difference is
    only a couple of grey levels, and the profile needs to survive it.
    Profiles are taken over the insert interior only, so the gold rim
    that the rectify padding pulls into frame contributes nothing.
    Returns (col_tone, col_edge, row_tone, row_edge).
    """
    x0, y0, x1, y1 = inner
    gray = cv2.createCLAHE(4.0, (8, 8)).apply(cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY))
    gray = cv2.GaussianBlur(gray, (5, 5), 0).astype(np.float32)
    grad_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=5))
    grad_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=5))
    trim_x, trim_y = int(0.04 * (x1 - x0)), int(0.04 * (y1 - y0))
    band_y = slice(y0 + trim_y, y1 - trim_y)
    band_x = slice(x0 + trim_x, x1 - trim_x)
    return (gray[band_y, :].mean(0), grad_x[band_y, :].mean(0),
            gray[:, band_x].mean(1), grad_y[:, band_x].mean(1))


def _cumulative(profile):
    norm = (profile - profile.min()) / (np.ptp(profile) + 1e-6)
    return np.concatenate([[0.0], np.cumsum(norm)]), len(profile)


def fit_axis(tone, edge, n, lo, hi):
    """Best (start, pitch) for `n` cavities between `lo` and `hi`.

    Two pieces of evidence, because neither alone survives all five
    inserts. Tone: cavity interiors are wide and uniform, the walls
    between them thin, so |wide band - thin band| is large only when the
    thin band actually sits on a wall. Taking the magnitude keeps it
    working whether the floors came out brighter than the walls or
    darker, which flips with the lighting. Edge: walls are creases, so
    the gradient spikes there and is flat inside a cavity - this is what
    pins down the 2-row boxes, where the tone signal has too few periods
    to be decisive on its own.
    """
    tone_cum, length = _cumulative(tone)
    edge_cum, _ = _cumulative(edge)

    def band_means(cum, starts, ends):
        lo_i = np.clip(np.floor(starts).astype(int), 0, length - 1)
        hi_i = np.clip(np.ceil(ends).astype(int), 1, length)
        hi_i = np.maximum(hi_i, lo_i + 1)
        return (cum[hi_i] - cum[lo_i]) / (hi_i - lo_i)

    index = np.arange(n)
    # only the walls *between* cavities: the outer two coincide with the
    # insert's own rim, whose hard edge would otherwise drag the grid
    # outwards until it swallowed the lip
    wall_index = np.arange(1, n) if n > 1 else np.arange(n + 1)
    span = hi - lo
    best, best_arg = -1e9, None
    # the cavity block always very nearly fills the insert - the moulded
    # lip around it runs 0-15% of the insert per side - so the pitch can
    # only be a narrow band around span/n. Without this the search
    # happily shrinks the grid onto any three tidy-looking creases.
    for pitch in np.arange(0.66 * span / n, 1.08 * span / n, 0.25):
        starts = np.arange(lo - 0.2 * pitch, hi - n * pitch + 0.2 * pitch + 0.1, 0.5)
        if not len(starts):
            continue
        in_lo = starts[:, None] + (index + 0.22) * pitch
        in_hi = starts[:, None] + (index + 0.78) * pitch
        wall_pos = starts[:, None] + wall_index * pitch
        wall_lo, wall_hi = wall_pos - 0.07 * pitch, wall_pos + 0.07 * pitch
        tone_score = np.abs(band_means(tone_cum, in_lo, in_hi).mean(1)
                            - band_means(tone_cum, wall_lo, wall_hi).mean(1))
        edge_score = (band_means(edge_cum, wall_lo, wall_hi).mean(1)
                      - band_means(edge_cum, in_lo, in_hi).mean(1))
        scores = tone_score + edge_score
        k = int(np.argmax(scores))
        if scores[k] > best:
            best, best_arg = float(scores[k]), (float(starts[k]), float(pitch))
    return best_arg, best


def detect_tray(bgr, rows, cols, long_side=900):
    """Full pipeline: photo in, `TrayLayout` out (None if no insert found)."""
    quad = detect_insert_quad(bgr)
    if quad is None:
        return None
    warp, H = rectify(bgr, quad, long_side=long_side)
    corners = cv2.perspectiveTransform(quad.reshape(1, 4, 2).astype(np.float32), H)[0]
    x0_in, y0_in = corners.min(0)
    x1_in, y1_in = corners.max(0)
    inner = (int(x0_in), int(y0_in), int(x1_in), int(y1_in))
    col_tone, col_edge, row_tone, row_edge = lattice_profiles(warp, inner)
    x_fit, x_score = fit_axis(col_tone, col_edge, cols, x0_in, x1_in)
    y_fit, y_score = fit_axis(row_tone, row_edge, rows, y0_in, y1_in)
    if x_fit is None or y_fit is None:
        return None
    x0, pitch_x = x_fit
    y0, pitch_y = y_fit
    cells = [(x0 + (c + 0.5) * pitch_x, y0 + (r + 0.5) * pitch_y, pitch_x, pitch_y)
             for r in range(rows) for c in range(cols)]
    return TrayLayout(quad=quad, H=H, size=(warp.shape[1], warp.shape[0]), cells=cells,
                      rows=rows, cols=cols, score=min(x_score, y_score))


RECT_LONG_SIDE = 900


def layout_to_record(layout, photo_shape):
    """Resolution-independent form of a layout, for the JSON cache."""
    h, w = photo_shape[:2]
    rect_w, rect_h = layout.size
    return {
        "rows": layout.rows,
        "cols": layout.cols,
        "score": round(layout.score, 4),
        "quad": [[float(x / w), float(y / h)] for x, y in layout.quad],
        "cells": [[cx / rect_w, cy / rect_h, cw / rect_w, ch / rect_h]
                  for cx, cy, cw, ch in layout.cells],
    }


def layout_from_record(record, photo_shape):
    h, w = photo_shape[:2]
    quad = np.array([[x * w, y * h] for x, y in record["quad"]], np.float32)
    H, (rect_w, rect_h) = rectify_matrix(quad, RECT_LONG_SIDE)
    cells = [(cx * rect_w, cy * rect_h, cw * rect_w, ch * rect_h)
             for cx, cy, cw, ch in record["cells"]]
    return TrayLayout(quad=quad, H=H, size=(rect_w, rect_h), cells=cells,
                      rows=record["rows"], cols=record["cols"],
                      score=record.get("score", 0.0))


def detect_at_scale(bgr, rows, cols, work_side=1100):
    """Detect on a downscaled copy, then express the result full-size."""
    scale = min(1.0, work_side / max(bgr.shape[:2]))
    work = cv2.resize(bgr, None, fx=scale, fy=scale) if scale < 1.0 else bgr
    layout = detect_tray(work, rows, cols, long_side=RECT_LONG_SIDE)
    if layout is None:
        return None
    return layout, work


def draw_layout(bgr, layout, cell_frac=0.9):
    """Overlay the detected insert and cavity slots on the original photo."""
    vis = bgr.copy()
    cv2.polylines(vis, [layout.quad.astype(int)], True, (0, 255, 0),
                  max(2, int(0.002 * max(vis.shape[:2]))))
    corners = []
    for cx, cy, cw, ch in layout.cells:
        half_w, half_h = cell_frac * cw / 2, cell_frac * ch / 2
        corners.append([[cx - half_w, cy - half_h], [cx + half_w, cy - half_h],
                        [cx + half_w, cy + half_h], [cx - half_w, cy + half_h]])
    quads = cv2.perspectiveTransform(np.array(corners, np.float32).reshape(1, -1, 2),
                                     layout.H_inv)[0].reshape(-1, 4, 2)
    for quad in quads:
        cv2.polylines(vis, [quad.astype(int)], True, (0, 255, 255),
                      max(1, int(0.0015 * max(vis.shape[:2]))))
        center = quad.mean(0).astype(int)
        cv2.circle(vis, tuple(center), max(3, int(0.004 * max(vis.shape[:2]))), (0, 0, 255), -1)
    return vis
