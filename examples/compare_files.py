"""Compare files — diff two images and produce a visual difference.

Run with:
    API2CONVERT_API_KEY=your-key python examples/compare_files.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

JPG_SMALL = "https://example-files.online-convert.com/raster%20image/jpg/example_small.jpg"
JPG = "https://example-files.online-convert.com/raster%20image/jpg/example.jpg"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    jobs = client.jobs
    try:
        job = jobs.create(
            {
                "process": True,
                "input": [
                    {"type": "remote", "source": JPG_SMALL},
                    {"type": "remote", "source": JPG},
                ],
                "conversion": [
                    {
                        "category": "operation",
                        "target": "compare-image",
                        "options": {"method": "ssim", "threshold": 5, "diff_color": "red"},
                    }
                ],
            }
        )
        finished = jobs.wait(job.id)
        outputs = jobs.outputs(job.id)
        print(f"Job {finished.id} status: {finished.status.code}, {len(outputs)} output(s)")
        for out in outputs:
            print(f"  {out.filename or out.id}: {out.uri}")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
