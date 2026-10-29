"""Privacy masks precede inference, ROI cropping and any retained preview."""
from dataclasses import replace
from io import BytesIO
from hashlib import sha256
from math import ceil

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


def preprocess(frame: FrameEnvelope, masks: list | tuple = (), roi=None, *, preview: bool = False,
               include_regions=(), exclude_regions=()) -> FrameEnvelope:
    with Image.open(BytesIO(frame.payload)) as original:
        image = original.convert("RGB")
    mask_image(image, masks)
    if include_regions or exclude_regions:
        selection = Image.new('L', image.size, 0 if include_regions else 255)
        draw = ImageDraw.Draw(selection)
        for areas, fill in ((include_regions, 255), (exclude_regions, 0)):
            for area in areas:
                x, y, width, height = rectangle(area)
                draw.rectangle((int(x * image.width), int(y * image.height),
                                min(image.width, ceil((x + width) * image.width)) - 1,
                                min(image.height, ceil((y + height) * image.height)) - 1), fill=fill)
        image = Image.composite(image, Image.new('RGB', image.size, 'black'), selection)
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
