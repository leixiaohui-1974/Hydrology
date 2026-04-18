"""确保 Hydrology/tests 可 import Hydrology/scripts 下的共用模块（如 rollout_gates_parse）。"""

from __future__ import annotations

import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parent.parent / "scripts"
_s = str(_scripts)
if _s not in sys.path:
    sys.path.insert(0, _s)
