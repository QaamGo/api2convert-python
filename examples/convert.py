"""Minimal end-to-end example.

Run with:  API2CONVERT_API_KEY=your-key python examples/convert.py path/to/file.docx pdf
"""

from __future__ import annotations

import sys

from api2convert import Api2Convert, Api2ConvertError

DEFAULT_SOURCE = "https://example-files.online-convert.com/raster%20image/jpg/example.jpg"


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE
    target = sys.argv[2] if len(sys.argv) > 2 else "png"

    client = Api2Convert()  # reads API2CONVERT_API_KEY
    try:
        result = client.convert(source, target)
        path = result.save(".")  # a directory -> keeps the server filename
        print(f"Saved: {path}")
    except Api2ConvertError as error:
        print(f"Conversion failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
