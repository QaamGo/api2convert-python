"""Presets — list saved conversion presets, filtered by category and target.

A preset is a reusable, named set of target + options.

Run with:
    API2CONVERT_API_KEY=your-key python examples/presets.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        presets = client.presets.list(category="video", target="mp4")
        print(f"Found {len(presets)} preset(s) for video/mp4")
        for preset in presets:
            print(f"  {preset.id}: {preset.name} -> {preset.target}")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
