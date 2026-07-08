"""Quickstart — convert a remote file, look the job up, and download the output.

Run with:
    API2CONVERT_API_KEY=your-key python examples/quickstart.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

SOURCE = "https://example-files.online-convert.com/raster%20image/jpg/example.jpg"
TARGET = "png"


def main() -> int:
    # Reads API2CONVERT_API_KEY; honours API2CONVERT_BASE_URL when set.
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        # 1) Convert the remote JPG to PNG (create -> start -> poll to completion).
        result = client.convert(SOURCE, TARGET)

        # 2) Look the finished job up by id.
        job = client.jobs.get(result.job.id)
        print(f"Job {job.id} status: {job.status.code}")

        # 3) Download the output to the current directory (keeps the server filename).
        path = result.save(".")
        print(f"Saved: {path} ({path.stat().st_size} bytes)")
    except Api2ConvertError as error:
        print(f"Conversion failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
