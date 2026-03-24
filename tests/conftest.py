from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_DIR = ROOT / "biba-controller"

if str(CONTROLLER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_DIR))


if "pigpio" not in sys.modules:
    sys.modules["pigpio"] = types.SimpleNamespace(OUTPUT=1, pi=object)
