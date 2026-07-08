"""Create hashes — compute a checksum of a file (SHA-256).

Run with:
    API2CONVERT_API_KEY=your-key python examples/create_hashes.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

ZIP = "https://example-files.online-convert.com/archive/zip/example.zip"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        result = client.convert(ZIP, "sha256", category="hash")
        # The hash file is small — read it directly.
        data = result.contents()
        print(f"SHA-256 result ({len(data)} bytes): {data.decode('utf-8', 'replace').strip()}")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
