"""Statistics — read your API usage for a given month.

Run with:
    API2CONVERT_API_KEY=your-key python examples/statistics.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

MONTH = "2026-06"  # yyyy-mm


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        stats = client.stats.month(MONTH)
        print(f"Usage for {MONTH}: {stats}")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
