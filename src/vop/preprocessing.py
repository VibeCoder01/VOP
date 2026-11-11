"""Privacy masks precede inference, ROI cropping and any retained preview."""
from dataclasses import replace
from io import BytesIO
from hashlib import sha256
from math import ceil

from PIL import Image, ImageDraw, ImageChops

from vop.contracts import FrameEnvelope, ProviderError
from vop.measurements import rectangle


def mask_image(image, masks):
    """Apply the same source privacy policy to inference, stills and live previews."""
    for mask in masks:
        x, y, width, height = rectangle(mask)
        ImageDraw.Draw(image).rectangle((int(x * image.width), int(y * image.height),
                                        min(image.width, int((x + width) * image.width + 0.999)),
                                        min(image.height, int((y + height) * image.height + 0.999))), fill="black")
    return image


def redaction_box(size, masks=(), roi=None, *, include_regions=(), exclude_regions=()):
    """Visible extent from configured geometry only, never scene brightness."""
    width, height = size
    if not masks and not include_regions and not exclude_regions and roi is None:
        return (0,0,width,height)
    visible = Image.new('L', size, 255)
    mask_image(visible, masks)
    if include_regions:
        included = Image.new('L', size, 0)
        draw = ImageDraw.Draw(included)
        for area in include_regions:
            x,y,w,h = rectangle(area)
            draw.rectangle((int(x*width),int(y*height),min(width,ceil((x+w)*width))-1,min(height,ceil((y+h)*height))-1),fill=255)
        visible = ImageChops.multiply(visible, included)
    draw = ImageDraw.Draw(visible)
    for area in exclude_regions:
        x,y,w,h = rectangle(area)
        draw.rectangle((int(x*width),int(y*height),min(width,ceil((x+w)*width))-1,min(height,ceil((y+h)*height))-1),fill=0)
    if roi is None:
        return visible.getbbox()
    x,y,w,h = rectangle(roi)
    box = (int(x*width), int(y*height), max(int(x*width)+1,int((x+w)*width)), max(int(y*height)+1,int((y+h)*height)))
    bounds = visible.crop(box).getbbox()
    return (bounds[0]+box[0],bounds[1]+box[1],bounds[2]+box[0],bounds[3]+box[1]) if bounds else None


def normalised_box(size, box):
    if box is None: return None
    w,h = size
    return [box[0]/w,box[1]/h,(box[2]-box[0])/w,(box[3]-box[1])/h]


def privacy_view(image, masks):
    size = image.size
    mask_image(image, masks)
    box = redaction_box(size, masks) if masks else (0,0,*size)
    return image.crop(box) if box else Image.new('RGB',(1,1),'black')


def preprocess(frame: FrameEnvelope, masks: list | tuple = (), roi=None, *, preview: bool = False,
               include_regions=(), exclude_regions=(), crop_redacted=True, require_visible=False) -> FrameEnvelope:
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
    if crop_redacted:
        box = redaction_box(image.size, masks, roi, include_regions=include_regions, exclude_regions=exclude_regions)
        if box is None:
            if require_visible:
                raise ProviderError('no_visible_image', 'All image areas are hidden. Review privacy, include/exclude and ROI settings.')
            image = Image.new('RGB', (1,1), 'black')
        else:
            image = image.crop(box)
    elif roi is not None:
        x,y,w,h = rectangle(roi)
        image = image.crop((int(x*image.width),int(y*image.height),max(int(x*image.width)+1,int((x+w)*image.width)),max(int(y*image.height)+1,int((y+h)*image.height))))
    if preview:
        image.thumbnail((1920, 1920))
    buffer = BytesIO()
    image.save(buffer, format="PNG")  # Removes EXIF/other original metadata.
    payload = buffer.getvalue()
    return replace(frame, payload=payload, width=image.width, height=image.height,
                   content_type="image/png", sha256=sha256(payload).hexdigest())
