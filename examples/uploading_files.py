"""Uploading files — one-call upload + convert of a LOCAL file.

Hand ``convert()`` a local path and it stages the job, streams the file to the
per-job upload server (authenticated with the job token, never your API key),
starts it and polls to completion.

Run with:
    API2CONVERT_API_KEY=your-key python examples/uploading_files.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from api2convert import Api2Convert, Api2ConvertError

# A minimal valid 1x1 PNG, so the example is self-contained (no fixture needed).
ONE_PX_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8cfc00000000301010018dd8db00000000049454e44ae426082"
)


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)

    tmp = Path(tempfile.gettempdir()) / "api2convert-example.png"
    tmp.write_bytes(ONE_PX_PNG)

    try:
        # Pass the local path — the SDK uploads it before converting.
        result = client.convert(str(tmp), "png")
        data = result.contents()
        print(f"Converted local file -> png ({len(data)} bytes)")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    finally:
        tmp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
