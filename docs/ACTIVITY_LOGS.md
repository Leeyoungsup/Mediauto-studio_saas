# Annotation and Upload Activity Logs

Authenticated annotation and upload operations append events to the existing
PostgreSQL audit log through the existing HMAC signing implementation. No new
table or database migration is required.

In Admin, open a user's activity dialog and select **Annotation** or **Uploads**.
The All badge counts all events for that user and date range. Upload events now
appear in Uploads rather than Files; existing historical `slide.upload` events
are included. The general audit-log action search also accepts the event names.

| Operation | Event |
| --- | --- |
| Tissue annotation save, including saved geometry/memo changes and deletion | `annotation.save` |
| Tissue annotation classes | `annotation_classes.update` (existing success event) |
| Cell annotation classes | `cell_annotation_classes.update` (existing success event) |
| Required/excluded regions save | `cell_annotation.regions_save` |
| Cell list save or completion | `cell_annotation.cells_save` |
| Patch annotation/review/termination state change or removal | `cell_annotation.status_update` |
| Clear slide patches | `cell_annotation.patches_clear` |
| Recompute patches from required regions | `cell_annotation.patches_recompute` |
| Save/delete a user's AI edits | `ai.annotation_save`, `ai.annotation_delete` |
| Upload session created | `slide.upload_started` |
| Upload completed and opened | `slide.upload` (existing event, extended with upload ID and chunk count) |
| Chunk processing failed | `slide.upload_chunk.failed` |

Handler failures use the operation event name with `.failed` appended, including
upload start, completion, annotation conflicts and class-save failures. These
events include the HTTP status and exception type, without copying the raw
exception message. Authentication and request-schema rejection happen before
the handler and are not captured by this logging wrapper.

New events include the authenticated user, timestamp, IP, user agent, resource
ID, outcome and bounded operation context. Summaries include counts returned by
the operation, tissue annotation revision before/after, and patch workflow
states before/after when available. Failed requests do not record a successful
after-state. A failure event describes the request outcome; it does not imply
that existing multi-step operations rolled back partial writes.

Annotation events describe saved requests, not every mouse movement or unsaved
edit. They do not contain full cell lists, polygon coordinates, memo text, or
individual shape diffs and are not a replacement for annotation backups.
Existing class-change events continue to contain the class definitions.

Successful chunks do not generate individual audit events. Start and completion
are correlated using `dict_context.upload_id` and `str_upload_id`, respectively;
chunk and completion failures also include `dict_context.upload_id`. A browser
that closes before sending another request has no explicit cancellation event.

Audit writes follow the existing best-effort management logging policy. A log
storage failure is reported in the server log and does not change the response
of an otherwise successful save or upload.

Restart the backend to load the new handlers and reload Admin to load the
updated activity UI. Existing records remain unchanged; missing historical
activity is not reconstructed.

Validation: backend 103 tests passed, including disposable PostgreSQL tests;
frontend 14 tests passed. Added HTTP-level tests cover annotation revisions and
conflicts, upload event correlation, chunk/start/completion failures, audit
storage failure, cell and AI edit events, and category queries. Frontend tests
cover escaped activity details and workflow/revision display. The live service
was not restarted as part of this change.
