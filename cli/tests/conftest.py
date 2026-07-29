from __future__ import annotations

import sys
from pathlib import Path


AGENT_HARNESS_DIR = Path(__file__).resolve().parents[3]

if str(AGENT_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_HARNESS_DIR))
