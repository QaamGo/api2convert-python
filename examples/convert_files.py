"""Convert files — browse the conversions catalog, then run a conversion.

Run with:
    API2CONVERT_API_KEY=your-key python examples/convert_files.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

SOURCE = "https://example-files.online-convert.com/raster%20image/jpg/example.jpg"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        # The full catalog: every supported target and its options.
        catalog = client.conversions.list()
        print(f"Catalog: {len(catalog)} conversions available")

        # Narrow it: which conversions produce a PNG?
        to_png = client.conversions.list(target="png")
        print(f"Conversions targeting png: {len(to_png)}")

        # Run one: convert the remote JPG to PNG.
        result = client.convert(SOURCE, "png")
        path = result.save(".")
        print(f"Saved: {path} ({path.stat().st_size} bytes)")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
