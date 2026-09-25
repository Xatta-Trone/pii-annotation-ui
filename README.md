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

Gold entities are stored as JSON:

```json
[{"text":"Blue Mountain Hospital","label":"MEDICAL_FACILITY","start_char":224,"end_char":246}]
```

Offsets use Python slicing conventions: start is inclusive and end is exclusive. Every saved entity must satisfy `clean_narrative[start_char:end_char] == text`. The browser component obtains offsets directly from the human selection; annotators never type offsets and repeated identical text remains independently selectable. Generative LLM outputs can later be aligned programmatically and are not expected to generate offsets.

## Workflow and status

Highlight narrative text, choose a label, and add the annotation. Gold annotations can be relabeled or deleted. Adjacent spans are allowed; overlapping and exact duplicate annotations are rejected.

- `NOT_ANNOTATED`: not finalized.
- `COMPLETED`: manually reviewed, including records with no PII (`gold_entities_json = []`).
- `NEEDS_REVIEW`: requires later attention.

Custom labels are normalized to `UPPERCASE_SNAKE_CASE`. They are recovered from valid gold entities when an exported dataset is uploaded again. Use **Download Annotated Dataset** for a complete portable checkpoint and re-upload that file to resume. **Download Label Schema** exports both default and custom labels.

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
