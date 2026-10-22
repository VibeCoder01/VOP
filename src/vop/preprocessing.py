"""Privacy masks precede inference, ROI cropping and any retained preview."""
from dataclasses import replace
from io import BytesIO
from hashlib import sha256

from PIL import Image, ImageDraw

from vop.contracts import FrameEnvelope
from vop.measurements import rectangle


def mask_image(image, masks):
    """Apply the same source privacy policy to inference, stills and live previews."""
    for mask in masks:
        x, y, width, height = rectangle(mask)
        ImageDraw.Draw(image).rectangle((int(x * image.width), int(y * image.height),
                                        min(image.width, int((x + width) * image.width + 0.999)),
                                        min(image.height, int((y + height) * image.height + 0.999))), fill="black")
    return image


def preprocess(frame: FrameEnvelope, masks: list | tuple = (), roi=None, *, preview: bool = False) -> FrameEnvelope:
    with Image.open(BytesIO(frame.payload)) as original:
        image = original.convert("RGB")
    mask_image(image, masks)
    if roi is not None:
        x, y, width, height = rectangle(roi)
        box = (int(x * image.width), int(y * image.height),
               max(int(x * image.width) + 1, int((x + width) * image.width)),
               max(int(y * image.height) + 1, int((y + height) * image.height)))
        image = image.crop(box)
    if preview:
        image.thumbnail((1920, 1920))
    buffer = BytesIO()
    image.save(buffer, format="PNG")  # Removes EXIF/other original metadata.
    payload = buffer.getvalue()
    return replace(frame, payload=payload, width=image.width, height=image.height,
                   content_type="image/png", sha256=sha256(payload).hexdigest())
