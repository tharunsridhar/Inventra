"""Converts inventra-demo.webm to inventra-demo.mp4 (H.264, plays everywhere and uploads to any host).

    uv run --no-project --with imageio-ffmpeg python make_mp4.py

imageio-ffmpeg ships a static ffmpeg binary, so nothing needs installing system wide.
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg

here = Path(__file__).parent
src, dst = here / "inventra-demo.webm", here / "inventra-demo.mp4"
subprocess.run(
    [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(src), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", "-an", str(dst)],
    check=True,
    capture_output=True,
)
print("saved", dst, f"({dst.stat().st_size // 1024} KB)")
