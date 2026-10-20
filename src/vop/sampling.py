"""Round-robin per-source sampling; one worker, no frame queue, independent of tabs."""
from threading import Event, Lock, Thread
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
        self.last_source = None
        self.pending = set()
        self.pending_lock = Lock()

    def request(self, source_id):
        """Coalesce one pending intent per camera; acquire its fresh frame on its turn."""
        with self.pending_lock:
            added = source_id not in self.pending
            self.pending.add(source_id)
            return added

    def requested(self, source_id):
        with self.pending_lock:
            return source_id in self.pending

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
        source_ids = list(self.pipeline.sources)
        with self.pending_lock:
            self.pending.intersection_update(source_ids)
        if self.last_source in source_ids:
            start = source_ids.index(self.last_source) + 1
            source_ids = source_ids[start:] + source_ids[:start]
        for source_id in source_ids:
            if self.stop_event.is_set():
                break
            control = self.pipeline.store.source_control(source_id)
            interval = control["sample_interval_seconds"]
            manual = self.requested(source_id)
            if not control["enabled"] or not self.pipeline.store.questions(source_id, active_only=True):
                self.deadlines.pop(source_id, None)
                with self.pending_lock:
                    self.pending.discard(source_id)
                continue
            if not manual and (interval == 0 or now < self.deadlines.get(source_id, 0)):
                continue
            if manual and self.pipeline.busy.locked():
                return  # Retain the intent until a fresh frame can be acquired.
            # A missed sample is dropped; never build a backlog or retry obsolete frames.
            self.deadlines[source_id] = now + interval
            self.last_source = source_id
            try:
                result = self.pipeline.run(source_id)
                failed = result["result"]["status"] != "success"
                self.failures[source_id] = self.failures.get(source_id, 0) + 1 if failed else 0
                if failed:
                    self.deadlines[source_id] = now + min(300, interval * 2 ** min(self.failures[source_id], 5))
                self.last_error = None
            except ProviderError as exc:
                self.last_error = exc.code
                if manual and exc.code == 'overloaded':
                    return
            except Exception:
                self.last_error = "sampling_failed"
            if manual:
                with self.pending_lock:
                    self.pending.discard(source_id)
            # One fresh frame per turn. Next tick starts after this input, so a slow
            # or failing camera cannot monopolise the worker while others are due.
            break

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                self.last_error = "sampling_failed"
            self.stop_event.wait(0.25)
