"""Extract assets — pull the embedded assets (images, etc.) out of a document.

Run with:
    API2CONVERT_API_KEY=your-key python examples/extract_assets.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

DOCX = "https://example-files.online-convert.com/document/docx/example.docx"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        result = client.convert(DOCX, "extract-assets", category="operation")
        outputs = result.outputs()
        print(f"Job {result.job.id} status: {result.job.status.code}, {len(outputs)} output(s)")
        for out in outputs:
            print(f"  {out.filename or out.id}: {out.uri}")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
