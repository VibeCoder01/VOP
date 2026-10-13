"""Generate only abstract shapes, never camera imagery."""
from pathlib import Path

from PIL import Image, ImageDraw


image = Image.new("RGB", (384, 256), "white")
draw = ImageDraw.Draw(image)
draw.rectangle((50, 70, 150, 170), fill="red")
draw.ellipse((220, 70, 320, 170), fill="blue")
output = Path(__file__).resolve().parents[1] / "fixtures" / "scene.png"
output.parent.mkdir(exist_ok=True)
image.save(output, optimize=False)
