"""Audio operations — re-encode audio (WAV -> AAC) with codec options.

Run with:
    API2CONVERT_API_KEY=your-key python examples/audio_operations.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError

WAV = "https://example-files.online-convert.com/audio/wav/example.wav"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        result = client.convert(
            WAV,
            "aac",
            {
                "audio_codec": "aac",
                "audio_bitrate": 192,
                "channels": "stereo",
                "frequency": 44100,
            },
            category="audio",
        )
        path = result.save(".")
        print(f"Saved audio: {path} ({path.stat().st_size} bytes)")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
