# Deletion and retained records

| Operation | Removed | Intentionally retained |
|---|---|---|
| Retire camera | Active use and pending automation work | Restorable camera setup, protected details and recorded history |
| Delete question | Recorded answers across versions, associated images/raw results, episodes, alerts/deliveries, action jobs for that question, test answers and cached summaries | Reserved ID, immutable configuration revisions and disabled rules/automations awaiting reassignment |
| Delete capture | Shared capture answers, raw result, saved image and affected alert/delivery data | Timestamp-only Unknown gap, configuration and audit |
| Delete input history | All captures, answers, gap markers, saved images, episodes and related delivery data, including empty captures and dangling frames | Camera/question/engine setup, audit and paused affected rules/automations |
| Delete action | Definition, stored audio, unused protected account; cancel waiting jobs | Self-contained Activity snapshots; an already sending action may finish |
| Delete automation | Definition and its state; cancel waiting jobs | Reusable actions and self-contained Activity snapshots |
| Delete engine profile | Inactive saved profile and its unused protected key | Current/shared configurations, recorded provenance and independently managed model files/workers |

Activity records contain their own action/context snapshots. They do not need a deleted
definition to remain readable. Immutable question/rule revisions and reserved question IDs
are deliberate records, not abandoned images or answers. Existing backups, exports and
already delivered messages are independent copies and are not withdrawn by deletion.

## Protected settings

Cleanup candidates are journalled in the same database transaction as configuration
deletion. Shared references in current, saved, retired and fallback configuration keep the
value alive. The dashboard key is always protected. An in-flight action keeps its account
until delivery finishes. Cleanup processes one candidate per pass, outside any database
writer transaction; a locked candidate is moved behind other candidates. Vault failures
remain pending, appear in Diagnostics and retry with a 30-second backoff. Restart preserves
the queue. Cleanup never sweeps arbitrary unreferenced values automatically.

Windows removes the canonical encrypted file and known legacy copies, preventing migration
from restoring a deleted key. Linux uses the existing Secret Service tooling and verifies
absence after clearing; locked matches stay pending. This accounts for libsecret clearing
only unlocked entries and reporting whether any were removed. [GNOME API documentation](https://gnome.pages.gitlab.gnome.org/libsecret/func.password_clearv_sync.html)
and [secret-tool implementation](https://github.com/GNOME/libsecret/blob/main/tool/secret-tool.c).
Linux verification output is discarded without logging values. No live Linux vault test
has been performed; offline contracts substitute the command responses.

## Read-only audit

```powershell
.\.venv\Scripts\python.exe tools\audit_deletions.py --check-vault
```

The tool opens the configured database read-only and enables SQLite query-only mode. It
checks foreign keys plus relationships not declared as foreign keys, dangling frames/audio,
waiting jobs, configuration references and answer residuals for deleted questions. The
optional Windows check compares canonical/legacy vault filenames with configured references;
it never decrypts them. Unknown external configurations are outside this workspace audit.
Nonzero review counts are evidence to investigate, not permission for an automatic sweep.
No network, model or camera access is performed. It does not compact or modify backups.

Server-side Tapo, email, SMS and **This computer** sound actions continue after browser
sign-in expires, provided VOP's process is running. **Browser** sound needs a signed-in,
visible tab with sound enabled; an unplayed browser job expires after two minutes.
