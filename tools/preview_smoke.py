"""Exercise the preview process boundary with explicit synthetic pixels only."""
from io import BytesIO
import json
from multiprocessing import active_children
from threading import Lock
from time import monotonic, sleep
from types import SimpleNamespace

from PIL import Image, ImageDraw

from vop.config import SourceSpec
from vop.contracts import utcnow
from vop.live_preview import LivePreviews, PreviewWorker, encode_preview


def synthetic_producer(connection, source):
    try:
        for number in range(100):
            pixels = Image.new('RGB', (1280, 720), 'white')
            ImageDraw.Draw(pixels).rectangle((0,0,639,719), fill='magenta')
            payload = encode_preview(pixels, [[0, 0, .5, 1], [.7, .25, .1, .5]])
            connection.send({'frame': (f'synthetic-{number}', payload, utcnow().isoformat())})
            sleep(.05)
    finally:
        connection.close()


def main():
    source = SourceSpec('synthetic-preview-process', 'Explicit synthetic preview fixture', 'usb', {'device': 0}, ())
    pipeline = SimpleNamespace(sources={source.source_id: source}, stopping=False, busy=Lock())
    previews = LivePreviews(pipeline, allowed=True, factory=lambda source: PreviewWorker(source, target=synthetic_producer))
    frames = set()
    pipeline.busy.acquire()  # Preview delivery must not depend on the inference slot.
    try:
        previews.leases[source.source_id] = monotonic() + 15
        deadline = monotonic() + 15
        while len(frames) < 5:
            assert monotonic() < deadline, 'Synthetic preview process timed out'
            previews.tick()
            image = previews.image(source.source_id)
            if image:
                frames.add(image[0])
                with Image.open(BytesIO(image[1])) as pixels:
                    assert pixels.size == (479, 540)  # Hidden left border removed before resizing.
                    assert pixels.getpixel((10, 10)) == (255, 255, 255)
                    assert pixels.getpixel((250, 250)) == (0, 0, 0)  # Interior redaction remains hidden.
            sleep(.02)
        child_pid = previews.workers[source.source_id].process.pid
        previews.leases[source.source_id] = 0
        previews.tick()
        assert not previews.workers
        assert child_pid not in {child.pid for child in active_children()}, 'Preview process remained alive'
    finally:
        previews.stop()
        pipeline.busy.release()
    print(json.dumps({'result': 'PASS', 'producer': 'explicit synthetic pixels', 'frames_received': len(frames),
                      'privacy_mask': 'verified', 'redacted_border_crop': 'verified', 'inference_slot': 'held throughout', 'expired_lease': 'child closed',
                      'model_weights': 'not_loaded', 'cameras': 'not_connected'}))


if __name__ == '__main__':
    main()
