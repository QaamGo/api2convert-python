"""Add a watermark — stamp one file onto another via a multi-input job.

Create a job with two remote inputs (the PDF to stamp and the PNG stamp), then
convert to PDF with the stamp options.

Run with:
    API2CONVERT_API_KEY=your-key python examples/add_watermark.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

PDF = "https://example-files.online-convert.com/document/pdf/example.pdf"
PNG = "https://example-files.online-convert.com/raster%20image/png/example.png"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    jobs = client.jobs
    try:
        job = jobs.create(
            {
                "process": True,
                "input": [
                    {"type": "remote", "source": PDF},
                    {"type": "remote", "source": PNG},
                ],
                "conversion": [
                    {
                        "category": "document",
                        "target": "pdf",
                        "options": {"stamp": True, "alignment": "center"},
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
