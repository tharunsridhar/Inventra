"""Builds inventra-demo.gif from the key frames saved by record.mjs (needs Pillow)."""
from pathlib import Path
from PIL import Image

here = Path(__file__).parent
files = sorted((here / "frames").glob("*.png"))
if not files:
    raise SystemExit("no frames found; run record.mjs first")

frames = []
for f in files:
    im = Image.open(f).convert("RGB")
    im = im.resize((960, round(im.height * 960 / im.width)), Image.LANCZOS)
    frames.append(im.quantize(colors=128, method=Image.Quantize.MEDIANCUT))

durations = [2500] * len(frames)
durations[-1] = 6000
frames[0].save(
    here / "inventra-demo.gif",
    save_all=True,
    append_images=frames[1:],
    duration=durations,
    loop=0,
    optimize=True,
)
print("saved", here / "inventra-demo.gif", f"({(here / 'inventra-demo.gif').stat().st_size // 1024} KB)")
