from pathlib import Path

from PIL import Image
import pytest

from vop.contracts import ProviderError
from vop.inputs.file_image import FileImageAdapter


@pytest.mark.parametrize("format,media", [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_decode_supported_without_modifying_file(tmp_path, format, media):
    path = tmp_path / "image.data"
    Image.new("RGB", (16, 12), "red").save(path, format=format)
    before = path.read_bytes()
    frame = FileImageAdapter().read(path, source_id="source-a")
    assert (frame.width, frame.height, frame.content_type) == (16, 12, media)
    assert frame.payload == before == path.read_bytes()
    assert frame.source_id == "source-a"


def test_missing_image_typed(tmp_path):
    with pytest.raises(ProviderError) as error:
        FileImageAdapter().read(tmp_path / "missing.png")
    assert error.value.code == "image_missing"


@pytest.mark.parametrize("payload", [b"", b"not an image", b"\x89PNG\r\n\x1a\n"])
def test_corrupt_image_typed(tmp_path, payload):
    path = tmp_path / "corrupt.png"
    path.write_bytes(payload)
    with pytest.raises(ProviderError) as error:
        FileImageAdapter().read(path)
    assert error.value.code == "image_corrupt"


def test_unsupported_format_typed(tmp_path):
    path = tmp_path / "disguised.png"
    Image.new("RGB", (10, 10)).save(path, format="GIF")
    with pytest.raises(ProviderError) as error:
        FileImageAdapter().read(path)
    assert error.value.code == "image_unsupported"


def test_import_ids_distinct_content_hash_stable():
    path = Path(__file__).resolve().parents[1] / "fixtures" / "scene.png"
    first, second = FileImageAdapter().read(path), FileImageAdapter().read(path)
    assert first.frame_id != second.frame_id
    assert first.sha256 == second.sha256
