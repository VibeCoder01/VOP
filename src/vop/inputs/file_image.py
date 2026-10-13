from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings

from PIL import Image, UnidentifiedImageError

from vop.contracts import FrameEnvelope, ProviderError, utcnow


class FileImageAdapter:
    def read(self, path: str | Path, source_id: str = "file-image") -> FrameEnvelope:
        try:
            with Path(path).open("rb") as stream:
                payload = stream.read(20 * 1024 * 1024 + 1)
        except FileNotFoundError as exc:
            raise ProviderError("image_missing", "Image file does not exist") from exc
        except OSError as exc:
            raise ProviderError("image_io", str(exc)) from exc
        return self.from_bytes(payload, source_id)

    def from_bytes(self, payload: bytes, source_id: str = "image-bytes") -> FrameEnvelope:
        if len(payload) > 20 * 1024 * 1024:
            raise ProviderError("image_too_large", "Image exceeds 20 MiB limit")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(payload)) as image:
                    if image.format not in ("JPEG", "PNG"):
                        raise ProviderError("image_unsupported", "Only JPEG and PNG are supported")
                    content_type = f"image/{'jpeg' if image.format == 'JPEG' else 'png'}"
                    width, height = image.size
                    image.verify()
                with Image.open(BytesIO(payload)) as image:
                    image.load()  # verify alone does not fully decode JPEG pixels
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError,
                Image.DecompressionBombWarning) as exc:
            raise ProviderError("image_corrupt", str(exc)) from exc
        stamp = utcnow()  # Imported image capture time is unknown; this is the import instant.
        return FrameEnvelope(source_id, str(uuid4()), stamp, stamp, content_type,
                             payload, width, height, sha256(payload).hexdigest())
