"""Bounded RTSP observation connections; continuously drain, return a new frame on demand."""
from dataclasses import replace
import multiprocessing
import os
from threading import Event, RLock, Thread

from vop.contracts import ProviderError, Status, utcnow
from vop.inputs.sources import camera_endpoint, camera_locator
from vop.inputs.file_image import FileImageAdapter

MAX_CONNECTIONS = 4


def camera_child(connection, source):
    with open(os.devnull, 'w') as quiet:
        os.dup2(quiet.fileno(), 1)
        os.dup2(quiet.fileno(), 2)
        capture = None
        try:
            import cv2
            capture = cv2.VideoCapture(camera_locator(source), cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not capture.isOpened():
                raise ProviderError('capture_open_failed', 'Camera could not be opened')
            while True:
                requested = connection.poll()
                if requested:
                    if connection.recv() != 'capture':
                        break
                # Read AFTER receiving the request. Never reuse a previously returned frame.
                if not capture.grab():
                    raise ProviderError('capture_read_failed', 'Camera returned no frame')
                stamp = utcnow()
                if requested:
                    ok, pixels = capture.retrieve()
                    if not ok or pixels is None:
                        raise ProviderError('capture_read_failed', 'Camera returned no frame')
                    ok, encoded = cv2.imencode('.png', pixels)
                    if not ok:
                        raise ProviderError('capture_encode_failed', 'Camera image could not be encoded')
                    frame = FileImageAdapter().from_bytes(encoded.tobytes(), source.source_id)
                    connection.send({'frame': replace(frame, captured_at_utc=stamp)})
        except ProviderError as exc:
            connection.send({'error': exc.code})
        except Exception:
            try:
                connection.send({'error': 'capture_failed'})
            except (OSError, EOFError):
                pass
        finally:
            if capture is not None:
                capture.release()
            connection.close()


class CameraWorker:
    def __init__(self, source):
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=camera_child, args=(child, source), daemon=True)
        try:
            self.process.start()
        except Exception:
            self.connection.close()
            raise
        finally:
            child.close()

    def capture(self, timeout):
        self.connection.send('capture')
        if not self.connection.poll(timeout):
            raise ProviderError('capture_timeout', 'Capture exceeded its deadline', Status.TIMEOUT)
        message = self.connection.recv()
        if 'error' in message:
            raise ProviderError(message['error'], 'Camera capture failed')
        return message['frame']

    def alive(self):
        return self.process.is_alive()

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=3)
        self.process.close()
        self.connection.close()


class PersistentCameras:
    def __init__(self, pipeline, *, allowed=False, factory=CameraWorker):
        self.pipeline, self.allowed, self.factory = pipeline, allowed, factory
        self.workers = {}
        self.lock, self.stop_event = RLock(), Event()
        self.thread = None

    def capture(self, source, capture_once):
        if (not self.allowed or source.kind != 'rtsp' or not source.sample_interval_seconds
                or not source.settings.get('persistent_capture', True)):
            self.clear(source.source_id)
            return capture_once(source)
        camera_endpoint(source)  # Validate destination even when reusing a connection.
        with self.lock:
            if self.stop_event.is_set() or self.pipeline.stopping:
                raise ProviderError('application_stopping', 'VOP is stopping')
            if self.thread is None:
                self.thread = Thread(target=self.loop, name='vop-camera-connections', daemon=True)
                self.thread.start()
            sid = source.source_id
            current = self.pipeline.sources.get(sid)
            if sid in self.workers and self.workers[sid][0] is not current:
                self.clear(sid)
            if sid not in self.workers:
                if len(self.workers) >= MAX_CONNECTIONS:
                    return capture_once(source)
                self.workers[sid] = (current, self.factory(source))
            try:
                return self.workers[sid][1].capture(self.pipeline.settings.capture_timeout_seconds)
            except Exception as exc:
                self.clear(sid)
                if isinstance(exc, ProviderError):
                    raise
                raise ProviderError('capture_failed', 'Camera connection interrupted') from None

    def clear(self, sid):
        with self.lock:
            if sid is None:
                for key in list(self.workers):
                    self.clear(key)
                return
            item = self.workers.pop(sid, None)
            if item:
                item[1].close()

    def tick(self):
        with self.lock:
            for sid, (source, worker) in list(self.workers.items()):
                control = self.pipeline.store.source_control(sid) if sid in self.pipeline.sources else None
                if (not worker.alive() or self.pipeline.sources.get(sid) is not source or not control or not control['enabled']
                        or not control['sample_interval_seconds'] or not source.settings.get('persistent_capture', True)
                        or not self.pipeline.store.questions(sid, active_only=True)):
                    self.clear(sid)

    def loop(self):
        while not self.stop_event.wait(1):
            try:
                self.tick()
            except Exception:
                # If controls cannot be checked, release connections rather than keep capturing.
                self.clear(None)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        with self.lock:
            for sid in list(self.workers):
                self.clear(sid)
