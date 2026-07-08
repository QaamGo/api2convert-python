"""Rate limits — inspect your account's contracts (quota / limits).

Run with:
    API2CONVERT_API_KEY=your-key python examples/rate_limits.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        contracts = client.contracts.get()
        print(f"Contracts: {contracts}")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
