# Gold PII Annotation Tool

A local Streamlit application for creating character-exact, human-verified PII annotations in transportation crash narratives. Weak PII candidates are displayed only as reference and are never promoted to gold automatically.

## Install and run from Windows Command Prompt

Install Python 3.11 or newer, download or clone this repository, and open Command Prompt in the folder that contains `app.py`. The project can be stored anywhere; no fixed download path is required.

Create and use a project-local virtual environment:

```cmd
py -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
rem Edit .env and replace the placeholder access codes.
.venv\Scripts\python.exe -m streamlit run app.py
```

If `py` is not recognized, use `python -m venv .venv` for the first command. All later commands deliberately use `.venv\Scripts\python.exe`, ensuring Streamlit, NumPy, and Pandas come from the isolated project environment rather than an incompatible global or Anaconda installation.

Do not use a bare `streamlit run app.py` command when multiple Python installations are present; it may invoke Streamlit from the wrong environment and produce errors such as `ImportError: numpy.core.multiarray failed to import`.

Open `http://localhost:8501` in a browser. Press `Ctrl+C` in Command Prompt to stop the server.

The application is protected by an access-code gate. Configure a long, random code in the untracked `.env` file:

```dotenv
PII_ANNOTATION_ACCESS_CODE=FIRST-ACCESS-CODE,SECOND-ACCESS-CODE
PII_ANNOTATION_SESSION_TTL_MINUTES=15
PII_ANNOTATION_ENVIRONMENT=local
PII_ANNOTATION_DB_PATH=
```

One or more codes may be configured in the same variable, separated by commas. Spaces surrounding each comma are ignored, empty entries are discarded, and each entered code is otherwise matched exactly and case-sensitively. For Streamlit Cloud, use valid TOML such as `PII_ANNOTATION_ACCESS_CODE = "FIRST-ACCESS-CODE,SECOND-ACCESS-CODE"`.

The same environment variable can be configured directly in the hosting environment. The app refuses to expose the upload or annotation interface when no usable code is configured. Authentication lasts for the current Streamlit browser session, and **Log out** is available in the sidebar. Access codes are never stored in the dataframe, URL, browser storage, or repository. `.env.example` is safe to commit; `.env` is ignored by Git.

`PII_ANNOTATION_SESSION_TTL_MINUTES` controls how many minutes an inactive temporary annotation session remains recoverable. It must be a positive whole number. If omitted, the app defaults to 15 minutes. Restart Streamlit after changing `.env`.

## Persistence modes

The app imports an uploaded CSV/TSV into SQLite once, then transactionally autosaves annotation changes, status, notes, labels, filters, and the current row. After a Streamlit restart, use the original session URL, re-upload the same source file, or choose the dataset under **Resume Saved Dataset**. Re-uploading the same source file is matched by its file hash and resumes the existing SQLite data instead of overwriting it.

By default both modes use this ignored project-root database:

```text
annotations.db
```

In `local` mode, `PII_ANNOTATION_DB_PATH` may optionally point to an existing or new SQLite database. When populated, the app opens and updates that database. When blank, it uses the project-root `annotations.db`. Prefer an unsynchronized path for important work; Box, OneDrive, Dropbox, and network filesystems can interfere with SQLite's database, WAL, and SHM files.

In `prod` mode, `PII_ANNOTATION_DB_PATH` is intentionally ignored and the app uses project-root `annotations.db`. Because the database and its WAL/SHM files are Git-ignored, a fresh production deployment starts with an absent database and creates fresh empty tables. Ordinary Streamlit reruns or process reloads within the same deployment reuse the existing file; the app never deletes it during startup.

CSV/TSV remains the import, export, and portable-backup format. It is not used as the live autosave store because changing one annotation would require rewriting the complete file; SQLite updates only the affected record atomically.

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

Arrow shortcuts are captured by one page-level listener, and browser key-repeat events are ignored, so one physical keypress advances exactly one record. Browser session routing updates activity silently to avoid component-driven rerun loops. If authentication is required, the requested `?session=...` URL is retained through the login form and restored after a successful login.

Changing a Gold label updates the row draft immediately. Left/Right arrow navigation also promotes a `NOT_ANNOTATED` record to `COMPLETED`; an existing `NEEDS_REVIEW` status is preserved. Leading and trailing whitespace from browser text selection is trimmed while offsets are adjusted, so the saved slicing invariant remains exact.

For large datasets, the complete downloadable CSV is cached by annotation revision and shared by the header and sidebar download buttons. It is invalidated whenever annotations, labels, status, or notes change, so a fresh complete dataset remains downloadable after every save without serializing all rows twice on every Streamlit rerun. Temporary server snapshots are likewise copied only after state changes; ordinary redraws only refresh the configured activity timeout.

## Temporary refresh recovery

Uploading a dataset creates a unique URL such as:

```text
http://localhost:8501/?session=FILE_HASH-TIMESTAMP
```

The working dataframe, draft annotations, notes, filters, labels, and current row are retained in the running Streamlit server's memory. The browser stores only the session key and last-activity time in per-tab `sessionStorage`; it does not store the narrative dataset in browser storage.

- Refreshing the page restores the current work automatically.
- Returning to the base app URL in the same browser tab redirects to the active session.
- A session expires after the configured inactivity timeout and is then removed from memory.
- **Start / Upload New Dataset** clears the browser route and returns to the upload screen. The old URL remains usable until its normal expiry.
- Restarting the Streamlit server clears all temporary URL sessions. Downloaded annotated datasets remain the authoritative durable backup.

Treat a live session URL as temporary access to the in-memory annotation session. Do not share it.

Run tests with:

```powershell
python -m pytest -q
```
