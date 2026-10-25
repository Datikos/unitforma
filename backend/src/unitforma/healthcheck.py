"""Container health probe: ``python -m unitforma.healthcheck live|ready``."""

from __future__ import annotations

import sys
import urllib.request


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "live"
    url = f"http://127.0.0.1:8000/internal/health/{kind}"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310 - fixed local URL
            return 0 if r.status == 200 else 1
    except Exception:  # noqa: BLE001
        return 1


if __name__ == "__main__":
    sys.exit(main())
