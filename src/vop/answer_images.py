"""Resolve a preview by answer provenance, never by the newest available image."""
from urllib.parse import quote


def answer_image_reference(store, pipeline, source_id, observation_ids):
    empty = {'frame':'', 'captured':'', 'url':'', 'message':'No processed image for the current answers.'}
    if not observation_ids or any(oid is None for oid in observation_ids):
        return empty
    with store.connection() as db:
        rows = db.execute('SELECT r.frame_id,o.captured_at_utc FROM observations o JOIN runs r ON r.id=o.run_id WHERE o.source_id=? AND o.id IN (' + ','.join('?' for _ in observation_ids) + ')',
                          (source_id,*observation_ids)).fetchall()
        frames = {row['frame_id'] for row in rows}
        if len(rows) != len(set(observation_ids)) or len(frames) != 1:
            return {**empty,'message':'Latest answers use different images. Inspect Individual Observations.'}
        frame_id = next(iter(frames))
        if frame_id is None:
            return {**empty,'message':'The latest observation did not capture an image.'}
        cached = pipeline.processed_previews.get(source_id)
        available = bool(cached and cached[0] == frame_id)
        if not available:
            available = db.execute('SELECT 1 FROM frames WHERE source_id=? AND frame_id=? AND evidence_png IS NOT NULL', (source_id,frame_id)).fetchone() is not None
    if not available:
        return {**empty,'message':'The answer image is not saved or is no longer available. A new observation will show it here.'}
    key = quote(frame_id,safe='')
    return {'frame':key,'captured':rows[0]['captured_at_utc'],'url':'/ui/processed-image/' + quote(source_id,safe='') + '/' + key,
            'message':'Privacy-masked source frame for the latest enabled answers.'}
