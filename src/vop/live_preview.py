"""Visible-page camera previews, separate from observation/inference and storage."""
from io import BytesIO
import multiprocessing
import os
from threading import Event, Lock, RLock, Thread
from time import monotonic
from uuid import uuid4

from PIL import Image

from vop.contracts import ProviderError, utcnow
from vop.inputs.sources import camera_endpoint, camera_locator
from vop.preprocessing import mask_image

FPS = 5
LEASE_SECONDS = 15
MAX_CAMERAS = 4


def encode_preview(image, masks):
    image = mask_image(image, masks)
    image.thumbnail((960, 540))
    buffer = BytesIO()
    image.save(buffer, format='JPEG', quality=80)
    return buffer.getvalue()


def preview_child(connection, source):
    # Native camera diagnostics can contain credentials. Keep them out of all logs.
    with open(os.devnull, 'w') as quiet:
        os.dup2(quiet.fileno(), 1)
        os.dup2(quiet.fileno(), 2)
        capture = None
        stop = Event()
        send_lock = Lock()
        try:
            import cv2
            locator = camera_locator(source)
            if source.kind == 'rtsp':
                capture = cv2.VideoCapture(locator, cv2.CAP_FFMPEG,
                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
            else:
                capture = cv2.VideoCapture(locator)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Backend-dependent hint; the reader also drains continuously.
            if not capture.isOpened():
                raise ProviderError('capture_open_failed', 'Camera could not be opened')
            latest = [None]

            def publish():
                previous = None
                try:
                    while not stop.wait(1 / FPS):
                        current = latest[0]
                        if current is not None and current is not previous:
                            payload = encode_preview(Image.fromarray(current[0][:, :, ::-1]), source.settings.get('privacy_masks', []))
                            with send_lock:
                                connection.send({'frame': (uuid4().hex, payload, current[1].isoformat())})
                            previous = current
                except Exception:
                    stop.set()

            Thread(target=publish, daemon=True).start()
            while not stop.is_set():
                ok, pixels = capture.read()
                if not ok or pixels is None:
                    raise ProviderError('capture_read_failed', 'Camera returned no frame')
                latest[0] = (pixels, utcnow())  # Replace, never queue obsolete decoder frames.
        except ProviderError as exc:
            with send_lock:
                connection.send({'error': exc.code})
        except Exception:
            with send_lock:
                connection.send({'error': 'preview_failed'})
        finally:
            stop.set()
            if capture is not None:
                capture.release()
            connection.close()


class PreviewWorker:
    def __init__(self, source, *, target=preview_child):
        self.source = source
        context = multiprocessing.get_context('spawn')
        self.receive, send = context.Pipe(duplex=False)
        self.process = context.Process(target=target, args=(send, source), daemon=True)
        try:
            self.process.start()
        except Exception:
            self.receive.close()
            raise
        finally:
            send.close()

    def poll(self):
        newest = None
        while self.receive.poll():
            message = self.receive.recv()
            if 'error' in message:
                raise ProviderError(message['error'], 'Preview connection failed')
            newest = message['frame']
        return newest

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join()
        self.process.close()
        self.receive.close()


class LivePreviews:
    def __init__(self, pipeline, *, allowed=False, factory=PreviewWorker):
        self.pipeline, self.allowed, self.factory = pipeline, allowed, factory
        self.leases, self.workers, self.images = {}, {}, {}
        self.progress, self.retry_at, self.failures, self.errors = {}, {}, {}, {}
        self.ready = set()
        self.suspended = set()
        self.lock, self.stop_event = RLock(), Event()
        self.thread = None

    def request(self, source_id):
        source = self.pipeline.sources.get(source_id)
        if not self.allowed or source is None or source.kind not in ('rtsp', 'usb'):
            raise ProviderError('preview_unavailable', 'Live preview is unavailable for this input')
        if source.kind == 'rtsp':
            camera_endpoint(source)  # Enforce destination policy before starting a process.
        with self.lock:
            if self.stop_event.is_set() or self.pipeline.stopping:
                raise ProviderError('application_stopping', 'VOP is stopping')
            self.leases[source_id] = monotonic() + LEASE_SECONDS
            if self.thread is None or not self.thread.is_alive():
                self.thread = Thread(target=self.loop, name='vop-live-preview', daemon=True)
                self.thread.start()

    def image(self, source_id):
        with self.lock:
            image = self.images.get(source_id)
            return (*image, 'live', 'image/jpeg') if image else None

    def state(self, source_id):
        with self.lock:
            if source_id in self.errors:
                return 'reconnecting'
            if source_id in self.workers:
                if source_id in self.ready:
                    return 'live' if monotonic() - self.progress[source_id] < 2 else 'reconnecting'
                return 'connecting'
            if source_id in self.leases:
                return 'connecting'
            return 'paused'

    def error(self, source_id):
        with self.lock:
            return self.errors.get(source_id, '')

    def clear(self, source_id):
        with self.lock:
            source_ids = set(self.leases) | set(self.workers) | set(self.images) if source_id is None else {source_id}
            for sid in source_ids:
                self.ready.discard(sid)
                for metadata in (self.leases, self.images, self.progress, self.retry_at, self.failures, self.errors):
                    metadata.pop(sid, None)
                worker = self.workers.pop(sid, None)
                if worker:
                    worker.close()

    def capture(self, source, capture_once):
        """Release exclusive USB devices during an observation's one-shot acquisition."""
        if source.kind != 'usb':
            return capture_once(source)
        with self.lock:
            self.suspended.add(source.source_id)
            worker = self.workers.pop(source.source_id, None)
            self.ready.discard(source.source_id)
            if worker:
                worker.close()
        try:
            return capture_once(source)
        finally:
            with self.lock:
                self.suspended.discard(source.source_id)

    def tick(self, now=None):
        now = monotonic() if now is None else now
        with self.lock:
            for metadata in (self.progress, self.retry_at, self.failures, self.errors):
                for sid in list(metadata):
                    if sid not in self.pipeline.sources:
                        metadata.pop(sid, None)
            for sid in list(self.images):
                if sid not in self.pipeline.sources:
                    self.images.pop(sid)
            for sid, worker in list(self.workers.items()):
                if self.leases.get(sid, 0) <= now or self.pipeline.sources.get(sid) is not worker.source:
                    worker.close()
                    self.workers.pop(sid)
                    self.ready.discard(sid)
                    self.retry_at.pop(sid, None)
                    if sid not in self.pipeline.sources:
                        self.images.pop(sid, None)
            for sid, expires in list(self.leases.items()):
                if expires <= now or sid not in self.pipeline.sources:
                    self.leases.pop(sid, None)
                    continue
                if sid in self.suspended:
                    continue
                try:
                    if sid not in self.workers:
                        if now < self.retry_at.get(sid, 0):
                            continue
                        if len(self.workers) >= MAX_CAMERAS:
                            self.errors[sid] = 'preview_capacity'
                            continue
                        self.workers[sid] = self.factory(self.pipeline.sources[sid])
                        self.progress[sid] = now
                    newest = self.workers[sid].poll()
                    if newest:
                        self.images[sid] = newest
                        self.ready.add(sid)
                        self.progress[sid] = now
                        self.failures[sid] = 0
                        self.errors.pop(sid, None)
                    elif now - self.progress[sid] > 10:
                        raise ProviderError('preview_timeout', 'Preview stalled')
                except Exception as exc:
                    if sid in self.workers:
                        self.workers.pop(sid).close()
                    self.ready.discard(sid)
                    self.errors[sid] = exc.code if isinstance(exc, ProviderError) else 'preview_failed'
                    self.failures[sid] = min(5, self.failures.get(sid, 0) + 1)
                    self.retry_at[sid] = now + min(30, 2 ** self.failures[sid])

    def loop(self):
        while not self.stop_event.wait(.05):
            self.tick()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        with self.lock:
            for worker in self.workers.values():
                worker.close()
            self.workers.clear()
            self.ready.clear()
            self.leases.clear()
            self.images.clear()
