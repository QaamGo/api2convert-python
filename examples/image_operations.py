"""Image operations — resize an image with the resize-image operation.

Run with:
    API2CONVERT_API_KEY=your-key python examples/image_operations.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

JPG = "https://example-files.online-convert.com/raster%20image/jpg/example.jpg"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        result = client.convert(
            JPG,
            "resize-image",
            {
                "width": 800,
                "height": 600,
                "resize_by": "px",
                "resize_handling": "keep_aspect_ratio_crop",
            },
            category="operation",
        )
        path = result.save(".")
        print(f"Saved resized image: {path} ({path.stat().st_size} bytes)")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
