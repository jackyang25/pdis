"""Container health probe for the ToolUniverse HTTP service."""

from __future__ import annotations

import json
import os
from urllib.request import urlopen


port = os.environ.get("PORT", "8080")
with urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
    body = json.loads(response.read().decode("utf-8"))
    if response.status != 200 or not isinstance(body, dict):
        raise SystemExit(1)
