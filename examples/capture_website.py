"""Capture a website — screenshot a URL and save it as a PNG.

The input uses the ``screenshot`` engine; the conversion renders the capture to
the target image format.

Run with:
    API2CONVERT_API_KEY=your-key python examples/capture_website.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    jobs = client.jobs
    try:
        job = jobs.create(
            {
                "process": True,
                "input": [
                    {
                        "type": "remote",
                        "source": "https://www.online-convert.com",
                        "engine": "screenshot",
                        "options": {
                            "screen_width": 1280,
                            "screen_height": 1024,
                            "device_scale_factor": 1,
                        },
                    }
                ],
                "conversion": [{"category": "image", "target": "png"}],
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
