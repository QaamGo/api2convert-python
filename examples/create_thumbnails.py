"""Create thumbnails — render a preview image of a document page.

Run with:
    API2CONVERT_API_KEY=your-key python examples/create_thumbnails.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

PDF = "https://example-files.online-convert.com/document/pdf/example.pdf"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        result = client.convert(
            PDF,
            "thumbnail",
            {"thumbnail_target": "png", "width": 300, "pages": "first", "dpi": 150},
            category="operation",
        )
        path = result.save(".")
        print(f"Saved thumbnail: {path} ({path.stat().st_size} bytes)")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
