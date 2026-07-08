"""Job lifecycle — drive create -> add input -> start -> wait -> outputs by hand.

``convert()`` is sugar over these primitives. Driving them yourself unlocks
compound jobs, custom inputs and step-by-step inspection.

Run with:
    API2CONVERT_API_KEY=your-key python examples/job_lifecycle.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

SOURCE = "https://example-files.online-convert.com/raster%20image/jpg/example.jpg"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    jobs = client.jobs
    try:
        # Stage a job (process=False) so we can attach inputs before starting.
        job = jobs.create(
            {"process": False, "conversion": [{"category": "image", "target": "png"}]}
        )
        print(f"Created job {job.id}")

        # Attach a remote input, then start processing.
        jobs.add_input(job.id, {"type": "remote", "source": SOURCE})
        jobs.start(job.id)

        # Poll to a terminal status, then read the outputs.
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
