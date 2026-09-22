# -*- coding: utf-8 -*-
"""Отрисовка Gerber-слоёв в PNG (headless, без KiCad GUI).

Использует pygerber (чистый Python + Pillow, без cairo).
Запуск: python scripts/gerber_render.py <каталог_с_герберами> [dpi]
Слои складываются в <каталог_с_герберами>/render/.
"""
import sys
from pathlib import Path

from pygerber.gerberx3.api.v2 import GerberFile
from pygerber.console.raster_2d_style import ColorScheme
from pygerber.common.rgba import RGBA

BLACK = RGBA(r=0, g=0, b=0, a=255)
GREEN = RGBA(r=40, g=143, b=40, a=255)
WHITE = RGBA(r=255, g=255, b=255, a=255)
YELLOW = RGBA(r=230, g=200, b=40, a=255)


def scheme(solid=GREEN, clear=GREEN, bg=BLACK):
    return ColorScheme(
        background_color=bg,
        clear_color=clear,
        solid_color=solid,
        clear_region_color=clear,
        solid_region_color=solid,
        debug_1_color=RGBA(r=171, g=171, b=171, a=255),
        debug_2_color=RGBA(r=125, g=125, b=125, a=255),
    )


LAYERS = [
    ("Gerber_TopLayer.GTL", scheme(GREEN, BLACK), "01_top_copper"),
    ("Gerber_BottomLayer.GBL", scheme(GREEN, BLACK), "02_bottom_copper"),
    ("Gerber_TopSilkscreenLayer.GTO", scheme(WHITE), "03_top_silkscreen"),
    ("Gerber_BottomSilkscreenLayer.GBO", scheme(WHITE), "04_bottom_silkscreen"),
    ("Gerber_TopSolderMaskLayer.GTS", scheme(WHITE), "05_top_mask"),
    ("Gerber_BottomSolderMaskLayer.GBS", scheme(WHITE), "06_bottom_mask"),
    ("Gerber_BoardOutlineLayer.GKO", scheme(YELLOW), "07_board_outline"),
]


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    dpi = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    out_dir = src / "render"
    out_dir.mkdir(exist_ok=True)
    dpmm = round(dpi / 25.4)

    for name, cs, stem in LAYERS:
        path = src / name
        if not path.exists():
            print("skip (нет файла):", name)
            continue
        out = out_dir / f"{stem}.png"
        try:
            GerberFile.from_file(str(path)).parse().render_raster(
                str(out), color_scheme=cs, dpmm=dpmm
            )
            print("OK:", out)
        except Exception as e:  # noqa: BLE001
            print("FAIL:", name, "->", repr(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
