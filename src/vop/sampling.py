"""Explicit per-source sampling; one worker, no queue, independent of browser tabs."""
from threading import Event, Thread
from time import monotonic

from vop.contracts import ProviderError


class Sampler:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.stop_event = Event()
        self.thread = None
        self.deadlines = {}
        self.failures = {}
        self.last_error = None

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = Thread(target=self.loop, name="vop-sampling", daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)

    def tick(self, now=None):
        now = monotonic() if now is None else now
        for source_id in list(self.pipeline.sources):
            control = self.pipeline.store.source_control(source_id)
            interval = control["sample_interval_seconds"]
            if not control["enabled"] or interval == 0 or not self.pipeline.store.questions(source_id, active_only=True):
                self.deadlines.pop(source_id, None)
                continue
            if now < self.deadlines.get(source_id, 0):
                continue
            # A missed sample is dropped; never build a backlog or retry obsolete frames.
            self.deadlines[source_id] = now + interval
            try:
                result = self.pipeline.run(source_id)
                failed = result["result"]["status"] != "success"
                self.failures[source_id] = self.failures.get(source_id, 0) + 1 if failed else 0
                if failed:
                    self.deadlines[source_id] = now + min(300, interval * 2 ** min(self.failures[source_id], 5))
                self.last_error = None
            except ProviderError as exc:
                self.last_error = exc.code
            except Exception:
                self.last_error = "sampling_failed"

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                self.last_error = "sampling_failed"
            self.stop_event.wait(0.25)
