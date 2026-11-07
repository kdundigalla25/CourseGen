# Calendar comparison and keeping a schedule

After generating section combinations, use **View option** and **Compare with** to compare two calendars on the same time scale. Select a week to see only meetings whose supplied dates include that weekday. Missing dates remain explicitly unverified; clearing the week shows an undated weekly pattern. All seven days are available by scrolling within each calendar. Fixed meetings are buttons with full course, section, weekday, time and date labels; keyboard activation opens details. The complete ranked section lists remain below the calendar.

Use **Use option N as preferred** to select the option that print and downloads will keep. Browsing another option does not change that choice. Editing progress, semester, course choices or preferences clears dependent results and the preferred choice. Session state stays in memory; there is no automatic browser storage.

## Dates and asynchronous courses

Times use `America/New_York`, independently of the browser's timezone. Meeting-specific date ranges take priority over term dates. When dates are missing, the calendar shows an explicitly unverified weekly pattern; ICS requires the user to supply fallback start/end dates. Fallback dates fill missing ranges and never override supplied source dates. Ranges are inclusive, ordered and limited to 366 days for export; at most 5,000 events are supported.

Asynchronous courses have no calendar blocks or invented all-day events. They remain in section lists, JSON and print. Mixed ICS exports name asynchronous courses in the calendar description; an asynchronous-only option has no ICS download. Holiday exceptions, cancellations and exam dates are not inferred from a weekly pattern. Verify those separately.

## Downloads and print

- **Print preferred schedule** prints the preferred option's full section list, supplied dates, term, timezone, source identifiers, rule versions, fictional-data notice and planning limits. It excludes the audit and other options. The browser controls PDF/printer output.
- **Download schedule JSON** creates a version-1 record of the chosen courses/sections, credit totals, preferences, term, provenance and warnings. It omits raw PDF text, reviewed audit, audit revision and course history. It cannot currently be imported to resume a planning session.
- **Download calendar ICS** creates one UTC event per actual fixed meeting occurrence, converting Chapel Hill wall-clock time with IANA timezone data. This preserves local meeting time across daylight-saving changes without assuming a recurring UTC offset. Ambiguous or nonexistent clock-change times are rejected for verification. Event IDs are stable for the same schedule, dataset and occurrence.

Exports use `POST /api/v1/schedules/export/{ics|json}` with a `ScheduleExportRequest`: the original generation request pinned to the returned snapshot digest and rule revisions, the chosen schedule ID, and optional paired fallback dates. The server reruns validation/generation and accepts only an option in those results. Stale provenance or unknown options must be regenerated. It does not accept client-supplied section details or retain files. Responses use attachment headers and `Cache-Control: no-store`; request bodies are capped at 2 MB. Public-hosting resource/rate controls remain future work.

ICS escaping, CRLF line endings, UTF-8 line folding and UTC event fields follow [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545). No external calendar account integration or calendar-app compatibility certification is claimed.

## Verification

Backend cases cover export revalidation, stale/unknown options, source-date precedence, missing/fallback dates, inclusive weekday occurrences, phased classes, daylight-saving transitions, midnight end times, nonexistent/ambiguous times, UTF-8 folding/escaping, asynchronous handling and omission of student history. Frontend cases cover date-only arithmetic, phased/undated rendering, preferred-option provenance and cancellation of a pending export after inputs change.

Run real Chromium checks from the repository root:

```powershell
npm.cmd --prefix frontend exec -- playwright install chromium
npm.cmd --prefix frontend run test:e2e
```

Playwright starts isolated local API/UI servers on ports 18766/18765, with no reuse of existing servers. It uses synthetic PDFs generated from representative parser fixtures; the 2026 browser-only variant explicitly adds an unmet Human Past label to exercise suggestions. The 2024 example uses manual sample-course search. The original parser fixtures and private PDFs are unchanged. Downloads and screenshots contain only synthetic records and are ignored by source control.

Both cohorts run at desktop and mobile widths through upload, confirmation, term/course selection, schedule generation, keyboard class details, comparison, preferred selection, JSON/ICS contents, print-media isolation, page-overflow checks, input invalidation and impossible-plan feedback. The optional private sample verifier separately checks both supplied original PDFs through scheduling and exports and prints aggregate results only. These checks are targeted, not a full accessibility audit or cross-browser certification.
