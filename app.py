"""Launch the checkout API + React UI.

    python app.py
    python backend/app.py --weights runs/detect/chocolate_model-2/weights/best.pt
"""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent / "backend" / "app.py"), run_name="__main__")
