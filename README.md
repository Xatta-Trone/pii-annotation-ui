# Gold PII Annotation Tool

A local Streamlit application for creating character-exact, human-verified PII annotations in transportation crash narratives. Weak PII candidates are displayed only as reference and are never promoted to gold automatically.

## Install and run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The compiled custom span selector is included. To rebuild it after editing its JavaScript:

```powershell
cd span_selector\frontend
npm install
npm run build
```

## Input data

Upload a UTF-8 `.csv` or `.tsv`. These columns are required:

- `crash_id`
- `clean_narrative`
- `weak_pii_entities_json`

If absent, `annotation_status`, `gold_entities_json`, and `annotator_notes` are added. Every other input column, every row, and original row order are preserved. All fields are read as strings so large crash IDs and leading zeros are not converted to floating point or scientific notation.

Current Gold datasets may also include `year`, `source_class`, `xxx_count`, `word_count`, `char_count`, `clean_redactedNarrative`, `adjudication_status`, `adjudication_notes`, `gold_reserve_type`, and `gold_reserve_version`. These and any additional source columns are preserved unchanged. Dataset length is never hard-coded; progress, filters, and navigation use the loaded row count.

Gold entities are stored as JSON:

```json
[{"text":"Blue Mountain Hospital","label":"MEDICAL_FACILITY","start_char":224,"end_char":246}]
```

Offsets use Python slicing conventions: start is inclusive and end is exclusive. Every saved entity must satisfy `clean_narrative[start_char:end_char] == text`. The browser component obtains offsets directly from the human selection; annotators never type offsets and repeated identical text remains independently selectable. Generative LLM outputs can later be aligned programmatically and are not expected to generate offsets.

## Workflow and status

Highlight narrative text, choose a label, and add the annotation. Gold annotations can be relabeled or deleted. Adjacent spans are allowed; overlapping and exact duplicate annotations are rejected.

The record view shows **Clean Narrative** and **Cleaned Redacted Narrative** side by side with synchronized proportional scrolling. `clean_narrative` remains the only selectable text and the only source of Gold offsets. Case-insensitive `xxx` placeholders are highlighted in the redacted comparison. Below the narratives, Gold controls and annotations appear in the left column and **Weak PII Reference** appears in the right column. Weak and Gold entities show compact `text (start, end)` offsets. Weak entities are never copied into Gold, and an empty weak list does not indicate that the narrative contains no PII or change annotation status.

- `NOT_ANNOTATED`: not finalized.
- `COMPLETED`: manually reviewed, including records with no PII (`gold_entities_json = []`).
- `NEEDS_REVIEW`: requires later attention.

Custom labels are normalized to `UPPERCASE_SNAKE_CASE`. They are recovered from valid gold entities when an exported dataset is uploaded again. Use **Download Annotated Dataset** for a complete portable checkpoint and re-upload that file to resume. **Download Label Schema** exports both default and custom labels.

Previous, Next, Save & Next, Mark Completed & Next, row jumps, crash-ID jumps, and the Left/Right arrow shortcuts all use the same save-before-navigation path. The current Gold entities (including relabels and deletions), status, and notes are synchronized to the working dataframe before the row changes. Arrow shortcuts are intentionally ignored while focus is inside an input, select box, text area, or editable field so normal cursor editing remains available.

Changing a Gold label updates the row draft immediately. Left/Right arrow navigation also promotes a `NOT_ANNOTATED` record to `COMPLETED`; an existing `NEEDS_REVIEW` status is preserved. Leading and trailing whitespace from browser text selection is trimmed while offsets are adjusted, so the saved slicing invariant remains exact.

For large datasets, the complete downloadable CSV is cached by annotation revision and shared by the header and sidebar download buttons. It is invalidated whenever annotations, labels, status, or notes change, so a fresh complete dataset remains downloadable after every save without serializing all rows twice on every Streamlit rerun. Temporary server snapshots are likewise copied only after state changes; ordinary redraws only refresh the 15-minute activity timestamp.

## Temporary refresh recovery

Uploading a dataset creates a unique URL such as:

```text
http://localhost:8501/?session=FILE_HASH-TIMESTAMP
```

The working dataframe, draft annotations, notes, filters, labels, and current row are retained in the running Streamlit server's memory. The browser stores only the session key and last-activity time in per-tab `sessionStorage`; it does not store the narrative dataset in browser storage.

- Refreshing the page restores the current work automatically.
- Returning to the base app URL in the same browser tab redirects to the active session.
- A session expires after 15 minutes without activity and is then removed from memory.
- **Start / Upload New Dataset** clears the browser route and returns to the upload screen. The old URL remains usable until its normal expiry.
- Restarting the Streamlit server clears all temporary URL sessions. Downloaded annotated datasets remain the authoritative durable backup.

Treat a live session URL as temporary access to the in-memory annotation session. Do not share it.

Run tests with:

```powershell
python -m pytest -q
```
