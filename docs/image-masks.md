# Question regions, camera privacy and automation markers

## Question mask

Open Configure → Questions → Edit (or New question). Select **Grab image** in Question
mask. The image comes from the saved camera connection. It is a camera-only request:
no inference, saved observation, retained evidence or GPU preparation is requested.
Grabs queue for the next free capture slot, even when monitoring is running or paused.
Opening the editor does not connect to the camera.
The Questions list shows **\*** beside questions with Include, Exclude or advanced
ROI areas. Hover over the marker to see which kinds are set; open Edit to change them.
Camera privacy alone does not add this question-specific marker.

- **Include areas**: draw one or more green rectangles. Only their combined area is
  visible to that question; everything outside is black. No include rectangles means
  the whole image is available.
- **Exclude areas**: red rectangles are blacked out for that question. Excludes take
  precedence where areas overlap. A question cannot reveal camera privacy areas.
- Remove individual areas, Undo changes or Clear areas. Coordinate entry provides a
  keyboard alternative; Enter there adds an area rather than saving the whole question.
  Coordinates are normalised fractions, measured from the top-left corner.
- Up to 16 include and 16 exclude rectangles per question. Rectangles must be finite,
  have positive dimensions and stay inside the image. Arbitrary polygons/brushes are not
  provided. Existing advanced ROI crops remain supported and appear as a blue outline.

Save the question to apply the areas. The mask is part of its immutable query policy,
so changing it creates a new question version and linked automations need review/save.
Old recordings retain their original policy. VOP 0.6.6 or later is required to read the
new query-policy fields; use the full database backup workflow when restoring them.

Camera privacy is applied first, then question includes/excludes, then optional ROI
cropping. Questions sharing exactly the same complete preprocessing policy share an
engine request. Different regions may require separate checks and make observations
slower; the existing overall inference deadline remains in force. The engine interface,
backend selection, source identity and remote authorization rules are unchanged.

The Observe answer image remains the common privacy-masked source frame. Per-question
regions alter the engine's input and are recorded in preprocessing provenance. A question
mask is not a camera-wide privacy setting and does not hide those areas in other questions.

## Camera privacy

Open Configure → Cameras → Manage camera → Privacy mask. Grabs use saved connection
details; save connection edits first. Draw red areas and **Save settings**. These areas
are hidden from all future live previews, editor grabs, inference inputs and saved evidence.
USB and RTSP masks persist across restart. USB grabs use the normal preview suspension
helper so the webcam decoder cannot hold the device open during capture.

Existing privacy areas are already black in a grab. Remove an area, save, then grab a
new image to see it again. Adding or removing privacy does not rewrite older retained
images. Use the existing history/retention deletion controls for those records.

Editor images are privacy-masked, in-memory snapshots (one per camera). They expire
after five minutes and are removed on access or the next scheduler tick. Capture failures
show a retry message. Wrong/expired image tokens do not return pixels. Saving privacy,
retiring a camera, deleting question/history data, retention cleanup or restart clears
relevant previews. A cleared/expired queued request cannot republish its old image.
Unsaved rectangle edits stay in the form until saved or the page is left.

## Asterisk in Observe

Open **Show answers**. Questions with one or more linked automations have `*` beside
their text. Hover for a count and paused/review-needed status. A newly queued automation
trigger highlights and pulses the star at one cycle per second for eight seconds.
Reduced-motion preferences use a steady highlight instead.

The expiry uses the trigger's original timestamp: refreshing answers does not restart the
eight-second window, and it ends even if later polling fails. Suppressed events, old jobs
and manual action tests do not flash it. Multiple actions from one trigger share the marker.
The marker indicates a trigger, not confirmed physical delivery; check Activity for results.
Marker changes invalidate the existing answer ETag without requiring a new observation.
