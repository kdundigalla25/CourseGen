# Structured parsing and review coverage

The parser extracts draft course attempts, requirement groups, reported statuses, numeric counts, starting-term evidence and independent program terms. [Curriculum resolution](CURRICULUM_RULES.md), [suggestions](RECOMMENDATIONS.md) and [scheduling](SCHEDULING.md) consume confirmed progress separately. Verified eligibility, weekly calendar comparison and export remain unimplemented.

## Local reference PDFs

The supplied PDFs remain private local references, not committed fixtures. Academic rows and boundaries were inspected locally. The optional sample check validates these aggregate expectations and selected metadata through the parsing/review endpoints:

| Reference | Pages | Career/start-term evidence | Major term | Course records | In progress | Requirement items |
| --- | --- | --- | --- | --- | --- | --- |
| Freshman | 3 | 2026 Fall | Business Administration: 2026 Fall | 27 | 6 | 73 |
| Junior | 4 | 2024 Fall | Computer Science BS: 2025 Fall | 54 | 5 | 66 |

Requirement counts include groups, leaf items, unknown policies and three degree-summary policies; tally duplicates are excluded. These are extraction counts, not remaining course/requirement counts. Potentially distinct duplicate credit awards are retained; repeated course references across blocks are linked.

First Year Data Lab / Power and Society versus Triple-I / Data Literacy / Power, Difference, and Inequality are preserved as future curriculum-identification evidence. These observations are not a verified complete signature or proof of an exact starting year from labels alone.

Optional local check (keep original files outside the repository):

```powershell
.\.venv\Scripts\python.exe backend/verify_local_samples.py --freshman "path\to\freshman.pdf" --junior "path\to\junior.pdf"
```

It checks identity-header removal, review, independent rule resolution, sample-data suggestions and schedule generation, printing only aggregate results. The freshman sample uses suggested DEMO courses; the junior sample exercises an explicitly chosen manual DEMO course because it has no outstanding automatically mapped course requirement. The app does not invent an unmet requirement to produce a recommendation. No UNC sections are invented. These sample checks do not establish perfect parsing of unseen layouts or every exception.

## Automated fixtures

`backend/tests/fixtures/cohort_2024.json` and `cohort_2026.json` contain synthetic records using representative public labels and observed formatting patterns. No full original history or personal identifiers are committed. Expected counts were enumerated separately from the parser. Tests cover wrapped/cross-page rows, delta/nonbreaking-space markers, counts, independent career/major terms, missing/conflicting metadata, satisfied-with-in-progress cases, repeated references/awards, course suffixes, credit/placement markers, unknown/failing grades, unrecognized prose, non-course events, tally exclusion and degree-summary columns.

Review tests cover acknowledgment, corrections, add/remove, link/hierarchy validation, reproducible revisions, recalculated evidence and unresolved flags. Frontend tests cover course-code entry, correction, deletion/link cleanup, count edits, errors and confirmation invalidation. Extraction error and privacy regression tests remain in place.

## Interpretation limits

The parser supports the observed credit/year/semester/grade endings and three hierarchy depths. Passing grades and TR/BE/PL credit markers establish completed/awarded evidence; blank grades require an explicit in-progress block elsewhere in the audit. Failing, temporary and unrecognized grades remain unknown. Completion evidence never overwrites reported requirement satisfaction.

Identical rows repeated within a block are retained as potentially distinct awards and flagged. Different topic titles/grade markers are not automatically merged. Conflicting grade references are flagged. Without source attempt IDs, repeated appearances do not prove official attempt identity.

Degree-summary policies without explicit status remain unknown even when numeric values appear sufficient. GPA, residency, admission, electives, events and unfamiliar conditions are not silently evaluated. Extra uninterpreted prose remains in evidence and is flagged. Original parsing flags remain available; confirmation distinguishes corrected versus still-unresolved flags. New unknown items added in review remain flagged.

## Operational limits

10 MB upload, 25 pages, 200,000 extracted characters, 500 structured attempts/requirements, 15 seconds per extraction worker, and two extraction workers per backend process. Record-limit truncation is flagged as incomplete. Review bodies are limited to 2 MB. Request bytes are capped before multipart parsing, uploads are closed, and extraction uses short-lived processes and pipes rather than retained student files.

These are local-development safeguards, not a hard process-memory sandbox. Public deployment still requires OS/container memory limits, request concurrency/rate limits and proxy configuration. No OCR is provided. Empty pages are flagged; entirely image-based documents fail with a clear explanation.

The observed university banner terminates later-page identity headers even when name/PID formatting differs from page one. Known preamble text and nine-digit identifiers are also removed from evidence. This is not general-purpose PDF redaction. Evidence and confirmed revisions remain sensitive and in browser memory only. Application errors/logs do not echo uploaded filenames or student records.
