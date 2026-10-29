"""Read-only integrity checks. Historical snapshots are not live configuration links."""
CHECKS = {
    'unreferenced_frames': 'SELECT count(*) FROM frames f WHERE NOT EXISTS(SELECT 1 FROM runs r WHERE r.source_id=f.source_id AND r.frame_id=f.frame_id)',
    'missing_current_question_version': 'SELECT count(*) FROM query_controls c WHERE NOT EXISTS(SELECT 1 FROM question_versions v WHERE v.source_id=c.source_id AND v.question_id=c.question_id AND v.version=c.current_version)',
    'question_controls_without_source': 'SELECT count(*) FROM query_controls c WHERE NOT EXISTS(SELECT 1 FROM sources s WHERE s.id=c.source_id)',
    'test_answers_without_question_version': 'SELECT count(*) FROM mock_values m WHERE NOT EXISTS(SELECT 1 FROM question_versions v WHERE v.source_id=m.source_id AND v.question_id=m.question_id AND v.version=m.version)',
    'events_without_question_version': 'SELECT count(*) FROM events e WHERE NOT EXISTS(SELECT 1 FROM question_versions v WHERE v.source_id=e.source_id AND v.question_id=e.question_id AND v.version=e.question_version)',
    'test_answers_for_deleted_questions': "SELECT count(*) FROM mock_values m JOIN release_settings s ON s.id='deleted_question:' || m.source_id || ':' || m.question_id",
    'observations_for_deleted_questions': "SELECT count(*) FROM observations o JOIN release_settings s ON s.id='deleted_question:' || o.source_id || ':' || o.question_id",
    'run_answers_for_deleted_questions': "SELECT count(*) FROM runs r,json_each(r.result_json,'$.answers') a JOIN release_settings s ON s.id='deleted_question:' || r.source_id || ':' || json_extract(a.value,'$.question_id')",
    'deliveries_without_alert': 'SELECT count(*) FROM deliveries d WHERE NOT EXISTS(SELECT 1 FROM alerts a WHERE a.id=d.alert_id)',
    'alerts_without_rule_revision': 'SELECT count(*) FROM alerts a WHERE NOT EXISTS(SELECT 1 FROM rule_versions r WHERE r.id=a.rule_id AND r.revision=a.rule_revision)',
    'rule_states_without_rule': "SELECT count(*) FROM rule_states s WHERE NOT EXISTS(SELECT 1 FROM rules r WHERE substr(s.id,1,length(r.id)+1)=r.id || ':')",
    'audio_without_action': 'SELECT count(*) FROM action_audio x WHERE NOT EXISTS(SELECT 1 FROM action_definitions a WHERE a.id=x.id)',
    'audio_actions_without_clip': "SELECT count(*) FROM action_definitions a WHERE json_extract(configuration,'$.kind')='audio' AND NOT EXISTS(SELECT 1 FROM action_audio x WHERE x.id=a.id)",
    'automations_without_action': "SELECT count(DISTINCT m.id) FROM automations m,json_each(m.configuration,'$.actions') a WHERE NOT EXISTS(SELECT 1 FROM action_definitions d WHERE d.id=a.value)",
    'waiting_jobs_without_action': "SELECT count(*) FROM action_jobs j WHERE status IN ('queued','retry') AND NOT EXISTS(SELECT 1 FROM action_definitions a WHERE a.id=j.action_id)",
    'waiting_jobs_without_automation': "SELECT count(*) FROM action_jobs j WHERE status IN ('queued','retry') AND automation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM automations m WHERE m.id=j.automation_id)",
}


def audit(db):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    issues, skipped = {}, []
    for name, sql in CHECKS.items():
        # Older backups can predate the optional Actions extension.
        if any(table not in tables and table in sql for table in ('action_audio','action_definitions','automations','action_jobs')):
            skipped.append(name)
            continue
        issues[name] = db.execute(sql).fetchone()[0]
    issues['foreign_key_violations'] = len(db.execute('PRAGMA foreign_key_check').fetchall())
    pending = db.execute("SELECT count(*) FROM release_settings WHERE id LIKE 'pending_secret_delete:%'").fetchone()[0]
    return {'result': 'PASS' if not any(issues.values()) and not pending else 'NEEDS_ATTENTION',
            'issues': issues, 'pending_secret_cleanup': pending, 'skipped_checks': skipped,
            'retained_by_design': 'Retired cameras, reserved question IDs, immutable revisions, audit, self-contained Activity snapshots and existing backups are not deleted by these checks.'}
