"""
Flavor names from labels.json
=============================

Every tray photo used to be a camera filename (IMG_1550.jpg, ...).
labels.json maps those originals to Cocoa Dolce flavor names. This
module is the one place that mapping is read, so a photo, a crop folder,
a sidecar and a YOLO class all agree on the same slug.

    Confetti Cake  ->  confetti_cake
    Crème Brûlée   ->  creme_brulee
    S'Mores        ->  smores
    Cookies & Cream -> cookies_and_cream

If two photos share a flavor name, the second file is named
<slug>_2.jpg so they don't collide. Distinct labels (Amaretto vs
Amaretto 2) stay separate classes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from paths import ROOT

LABELS_PATH = ROOT / "labels.json"


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def camera_key(name: str) -> str:
    """IMG_1550.jpg, img_1550, IMG_1550_pieces -> img_1550."""
    stem = Path(name).stem
    stem = re.sub(r"_(pieces|overlay|sheet)$", "", stem, flags=re.I)
    match = re.match(r"(img_\d+)", stem, flags=re.I)
    return match.group(1).lower() if match else slugify(stem)


def load_labels(path=LABELS_PATH):
    """camera key -> display name, in file order."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {camera_key(filename): label for filename, label in data.items()}


def photo_stems(labels=None):
    """camera key -> unique filename stem (amaretto, amaretto_2, ...)."""
    labels = labels if labels is not None else load_labels()
    seen = {}
    stems = {}
    for camera, label in labels.items():
        slug = slugify(label)
        count = seen.get(slug, 0) + 1
        seen[slug] = count
        stems[camera] = slug if count == 1 else f"{slug}_{count}"
    return stems


def photo_stem(camera_or_path, labels=None):
    labels = labels if labels is not None else load_labels()
    key = camera_key(camera_or_path)
    return photo_stems(labels).get(key) or slugify(Path(camera_or_path).stem)


def flavor_for_image(path, labels=None):
    """Class slug for a tray photo. Falls back to the filename."""
    labels = labels if labels is not None else load_labels()
    key = camera_key(path)
    if key in labels:
        return slugify(labels[key])
    stem = Path(path).stem
    unique = set(slugify(v) for v in labels.values())
    base = re.sub(r"_\d+$", "", stem)
    if stem in unique or base in unique:
        return base if base in unique else stem
    return slugify(stem)


def display_name(slug, labels=None):
    labels = labels if labels is not None else load_labels()
    for label in labels.values():
        if slugify(label) == slug:
            return label
    return slug


def unique_class_slugs(labels=None):
    labels = labels if labels is not None else load_labels()
    return sorted({slugify(label) for label in labels.values()})


def match_marketing_stem(stem, labels=None):
    """Best flavor slug for a Cocoa Dolce product-photo filename."""
    labels = labels if labels is not None else load_labels()
    cleaned = slugify(re.sub(r"_?600x$", "", stem, flags=re.I))
    aliases = {
        "banana_foster_dark_chocolate": "bananas_froster",
        "earl_grey_honey_gourmet_chocolate": "tea_and_honey",
        "bourbon_barrel_maple_cream_chocolate": "maple_cream",
    }
    if cleaned in aliases:
        return aliases[cleaned]
    slugs = unique_class_slugs(labels)
    if cleaned in slugs:
        return cleaned
    compact = cleaned.replace("_", "")
    hits = [slug for slug in slugs if slug in cleaned or slug.replace("_", "") in compact]
    if not hits:
        return None
    return max(hits, key=len)
