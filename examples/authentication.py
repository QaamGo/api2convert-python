"""Authentication — verify your API key by making an authenticated call.

Listing your jobs is a cheap authenticated request: it succeeds with a valid key
and raises AuthenticationError with a bad one.

Run with:
    API2CONVERT_API_KEY=your-key python examples/authentication.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError, AuthenticationError


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        jobs = client.jobs.list()
        print(f"Authenticated. Your account has {len(jobs)} recent job(s) on this page.")
    except AuthenticationError:
        print("Authentication failed: check your API2CONVERT_API_KEY.", file=sys.stderr)
        return 1
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
