#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from pathlib import Path

PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")
root = Path(__file__).parents[1]
text = (root / "k8s" / "app.yaml").read_text()
missing = sorted({key for key in PATTERN.findall(text) if not os.getenv(key)})
if missing:
    raise SystemExit(f"Missing deployment variables: {', '.join(missing)}")
print(PATTERN.sub(lambda match: os.environ[match.group(1)], text))
