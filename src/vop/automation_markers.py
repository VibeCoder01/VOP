"""Small, recent queue lookups; a trigger marker is not a delivery confirmation."""
from datetime import timedelta
import json

from fasthtml.components import Span

from vop.contracts import utcnow
from vop.measurements import utc

FLASH_SECONDS = 8


def markers(store, source_id, versions):
    now = utcnow()
    result = {}
    with store.connection() as db:
        paused = db.execute("SELECT value_json FROM release_settings WHERE id='actions_paused'").fetchone()
        paused = bool(paused and json.loads(paused[0]))
        rows = db.execute("SELECT id,configuration FROM automations WHERE json_extract(configuration,'$.source_id')=?", (source_id,)).fetchall()
        for row in rows:
            config = json.loads(row['configuration'])
            qid = config['question_id']
            if qid not in versions: continue
            item = result.setdefault(qid, {'count':0, 'enabled':0, 'until':0})
            item['count'] += 1
            item['enabled'] += int(config['enabled'] and not paused and config['question_version'] == versions[qid])
            recent = db.execute("""SELECT MAX(created) FROM action_jobs WHERE automation_id=? AND created>=? AND created<=?
                AND status!='suppressed' AND json_extract(context,'$.source_id')=?
                AND json_extract(context,'$.question_id')=? AND json_extract(context,'$.question_version')=?""",
                (row['id'], (now-timedelta(seconds=FLASH_SECONDS)).isoformat(), now.isoformat(), source_id, qid, versions[qid])).fetchone()[0]
            if recent:
                item['until'] = max(item['until'], int((utc(recent)+timedelta(seconds=FLASH_SECONDS)).timestamp()*1000))
    return result


def marker(info):
    if not info: return None
    label = f"{info['count']} linked automation" + ('s' if info['count'] != 1 else '')
    if not info['enabled']: label += '. Paused or needs review'
    if info['until']: label += '. Triggered recently; see Activity for the delivery result'
    return Span('*', cls='automation-marker' + (' is-triggered' if info['until'] else ''),
                title=label, aria_label=label, data_automation_until=info['until'] or None)


SCRIPT = """function armAutomationMarkers(panel) {
  for (const marker of panel.querySelectorAll('[data-automation-until]')) {
    const remaining=Number(marker.dataset.automationUntil)-Date.now();
    if(remaining<=0) marker.classList.remove('is-triggered');
    else if(!marker.dataset.armed){
      marker.dataset.armed='true';
      setTimeout(()=>marker.classList.remove('is-triggered'),Math.min(remaining,8000));
    }
  }
}
"""

CSS = """.automation-marker{display:inline-block;margin-left:6px;font-weight:800;font-size:18px;color:#0055b3}.automation-marker.is-triggered{color:#9e5400;animation:automation-pulse 1s ease-in-out 8}@keyframes automation-pulse{0%,100%{opacity:1}50%{opacity:.25}}@media(prefers-reduced-motion:reduce){.automation-marker.is-triggered{animation:none}}
"""
