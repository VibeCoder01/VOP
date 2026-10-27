# Actions and Automations (Phase 5)

Configure mode has separate **Actions** and **Automations** pages. View mode has
**Activity**, with results refreshed once per second without a page reload.
No actions, destinations or enabled automations are created automatically.

## First use

1. Configure → Actions → Add action. Choose a type, then enter its relevant settings.
2. Save. For Tapo, **Check device** reads device information without changing the light
   or playing a sound. For H100 it also loads the available sound choices.
3. **Test action** deliberately queues the real action. Read its result in Activity.
4. Automations → Add automation. Choose a camera/question and trigger, select one or
   more actions, set limits, and **Preview automation**. Preview does not save or execute.
5. Save as Enabled when ready. New automations default to Paused. Start camera monitoring
   separately; enabling an automation does not start capture or inference.

The current editor connects one camera/question per automation. Reuse the same named
action in other automations to cover additional cameras. Cameras, questions and actions
are named choices; there is no scripting or graphical wiring language.

## Sound destination

**This browser:** select **Enable sound** in the sidebar. It plays a short confirmation
beep. The preference stays in that tab while navigating; browser autoplay rules may require
another click after a reload. Keep at least one enabled, visible VOP tab open. One browser
claims each sound, so two enabled tabs do not both play it. A closed/unresponsive tab is not
automatically reassigned: this avoids duplicate playback. Browser sounds expire after
00:02:00 if unclaimed. Disable sound stops playback in that tab.

**The VOP computer:** currently Windows only. Sound plays on the computer running the
dashboard, not necessarily the camera or GPU worker. Its audio device/system volume must
be available. Beeps and audio use the configured amplitude, with system volume applied.

Audio uploads use PCM WAV, 16-bit mono/stereo, 8–48 kHz, maximum 00:01:00 and 2 MB.
JavaScript is needed to upload. The audio bytes are stored in the database and full backups;
configuration JSON does not contain audio bytes.

## Tapo L530 and H100

Install the optional, pinned adapter on the dashboard computer:

```powershell
.\.venv\Scripts\python.exe -m pip install ".[tapo]"
```

Restart VOP. The implementation uses **python-kasa 0.12.0**, a community library.
For a portable installation without a source checkout, install `python-kasa==0.12.0`
directly with that installation's Python instead of the `.[tapo]` extra.
Enter the private LAN IPv4 address and **Tapo account** email/password in the protected
fields, not the camera's RTSP credentials. Different firmware/account configurations may
affect compatibility. These models are targets, not a claim that your hardware was tested.

L530 actions: on, off, or bounded one-second on/off pulses; optional brightness and colour.
Flash finishes **off** rather than restoring a stale state. A device/network failure or
process/power loss can interrupt cleanup and leave a light on; Activity reports ambiguous
results as uncertain. An action already in progress may finish after pause or deletion.

H100 actions: the hub's current sound or a sound read with Check device, Low/Normal/High
volume and duration 00:00:01–00:00:30. The device receives the duration in its play command;
VOP does not change the hub's saved alarm defaults. H100 built-in sounds are separate from
uploaded WAV playback. It does not upload WAV files to the hub.

References: [python-kasa tutorial](https://python-kasa.readthedocs.io/en/stable/tutorial.html),
[alarm implementation](https://github.com/python-kasa/python-kasa/blob/0.12.0/kasa/smart/modules/alarm.py),
[supported devices](https://github.com/python-kasa/python-kasa/blob/0.12.0/SUPPORTED.md).

## Email and SMS

Email uses authenticated **SMTP over TLS** (normally port 465). STARTTLS-only servers are
not supported in this release. Enter one sender and one recipient, account and password/app
password in protected setup. Use additional named actions for other recipients.

SMS uses the fixed Twilio HTTPS Messages API and API-key authentication. Supply the Account
SID (AC…), API key SID (SK…), secret and international sender/recipient numbers. Your provider
account must have an SMS-capable sender and any necessary recipient permissions. Trial
restrictions and message/segment charges apply. No inbound webhook or public VOP endpoint
is required for outbound messages. VOP does not currently poll delivery receipts.

Messages support literal `{camera}`, `{question}`, `{trigger}`, `{automation}` substitutions.
No executable expressions, raw provider scores, image attachments or arbitrary scripts.
**Accepted** means the mail server or Twilio accepted the message, not that it reached a
person's inbox or phone. Only a definitive Twilio 429 rejection is retried, at most three
attempts within the original expiry. Timeouts and interrupted sends are **uncertain** and
are not automatically resent. Check the destination before testing again.

[Twilio Messages API](https://www.twilio.com/docs/messaging/api/message-resource)
and [authentication](https://www.twilio.com/docs/messaging/api).

## Trigger semantics and limits

- Start/end/duration use confirmed Yes/No episodes, not individual positive frames.
- End requires a confirmed closed episode. UNKNOWN/interrupted episodes never mean all clear.
- Duration uses accumulated observed intervals; it does not extrapolate unobserved time.
- Answer becomes supports named choices, ordinal level names/numbers and Yes/No. UNKNOWN
  suspends matching; a return to the same matching value does not trigger another action.
- Unavailable/recovered refer to the question's observation state, including stale samples
  and failed inference. These health triggers require monitoring to be running; an intentional
  monitoring pause is not a device failure. They are separate from confirmed episode endings.
- Ordinal value triggers compare the returned numeric position **at or above** or **at or
  below** the selected named level. Fractional positions do not need to equal a whole level.
- A daily schedule uses the workspace timezone, including overnight windows. Equal times
  mean all day. Cooldown and hourly limits apply per automation, across its selected actions.
- Suppressed events are recorded, not delayed until the cooldown/schedule ends.
- Stable transition/action keys prevent repeated polling from duplicating queued actions.
  Queue claims prevent concurrent browsers/server delivery from taking the same job.
- Saving/editing, restarting, or resuming starts from current conditions. Old history and
  old duration episodes are not replayed. Historical recomputation cannot issue old actions.
- New jobs expire after 00:02:00. Startup expires waiting jobs and marks interrupted sends
  uncertain. Physical delivery cannot offer an exactly-once guarantee across crashes.
- Pause automations cancels waiting automatic actions but not explicit manual tests.
  In-progress actions may finish. Camera monitoring continues independently.
- Disabled/retired/deleted cameras/questions cancel waiting actions. Question changes require
  reviewing and saving the automation for the new version. Deleting question/history data
  also removes related action activity and pauses affected automations. Messages already sent
  and saved backups cannot be withdrawn.
- Synthetic observations never execute automatic actions. Explicit action tests remain usable.

Capture/inference never waits for action delivery. The single action worker processes device
and messaging commands in order; a long sound/flash can delay later actions. Browser sound
claims are separate. Temporal replay is cached per camera/question until history/policy
changes, with staleness checked independently. Unchanged idle cycles do not acquire a writer
lock. Existing full-history replay on new samples remains a separate performance limitation.

## Persistence and recovery

Definitions, automations, queue and uploaded WAVs are in the existing SQLite database using
an additive Actions storage extension (version 1, recorded in release_settings). Existing
Phase 4 schema version 3 and backup validation remain compatible. Full database backups
include this extension. Configuration exports include action/automation definitions and
secret references; restoring definitions/audio is currently via **full backup**, not JSON
import. Secrets stay in the operating-system vault and must be supplied separately on another
machine/account. Old VOP versions do not run these actions; use VOP 0.6.0 or later.

Offline tests intercept delivery and use synthetic inputs. They never turn on lights, sound
a hub, play audio, send email/SMS or load a real model. Hardware/provider acceptance is a
separate explicit test using the buttons above.
