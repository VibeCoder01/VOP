"""Local monotonic timings; no images, credentials or cross-host clock subtraction."""
from contextlib import contextmanager
from time import perf_counter
from statistics import median
from math import ceil

from vop.contracts import utcnow


LABELS = {'engine_ready': 'Check / start engine', 'capture': 'Acquire camera image',
          'prepare_image': 'Prepare images and masks', 'engine_request': 'Engine request (round trip)',
          'save': 'Save result', 'total': 'Total observation', 'provider': 'Provider inference (within request)'}


class StageTimings:
    def __init__(self, source_id, engine_id=None, engine_version=None, synthetic=None):
        self.source_id = source_id
        self.engine_id, self.engine_version, self.synthetic = engine_id, engine_version, synthetic
        self.started = perf_counter()
        self.measured_at = utcnow().isoformat()
        self.values = {}
        self.provider_ms = None
        self.status = 'incomplete'

    @contextmanager
    def stage(self, name):
        started = perf_counter()
        try:
            yield
        finally:
            self.values[name] = self.values.get(name, 0) + (perf_counter() - started) * 1000

    def snapshot(self):
        return {'source_id': self.source_id, 'engine_id': self.engine_id,
                'engine_version': self.engine_version, 'synthetic': self.synthetic,
                'started_at_utc': self.measured_at,
                'status': self.status, 'stages_ms': dict(self.values),
                'total_ms': (perf_counter() - self.started) * 1000, 'provider_ms': self.provider_ms}


def summarise(samples):
    """Successful attempts only for percentiles; keep the latest attempt visible."""
    successful = [s for s in samples if s['status'] == 'success']
    rows = []
    for key, label in LABELS.items():
        def value(sample):
            return sample.get(key + '_ms') if key in ('total', 'provider') else sample['stages_ms'].get(key)
        values = sorted(v for s in successful if (v := value(s)) is not None)
        rows.append({'stage': label, 'latest_ms': value(samples[-1]) if samples else None,
                     'count': len(values), 'median_ms': median(values) if values else None,
                     'p95_ms': values[max(0, ceil(.95 * len(values)) - 1)] if values else None})
    return {'attempts': len(samples), 'successes': len(successful), 'rows': rows,
            'latest_started': samples[-1]['started_at_utc'] if samples else None,
            'latest_status': samples[-1]['status'] if samples else None}
