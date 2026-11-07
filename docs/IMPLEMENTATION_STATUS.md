# Calendar comparison and export handoff

Milestones 1–6 functionality is implemented within documented partial coverage. Weekly calendar comparison, preferred selection, print and JSON/ICS exports are available. The review experience remains a working version; [the owner's UX note](REVIEW_UX_IDEAS.md) stays open without a redesign in this increment.

Implemented:

- React upload and extraction inspection screen with responsive styling, keyboard-accessible controls, status/error messaging, page text and session clearing.
- FastAPI health and PDF extraction endpoints, generated OpenAPI/TypeScript contracts, and initial audit/course/section models.
- Killable extraction worker, upload/page/text/time limits, bounded extraction concurrency, upload closure and no retained student documents.
- Structured attempts, requirement groups, reported statuses, source counts and page/line evidence.
- Independent starting-term evidence, catalog label, and degree/major/minor terms, with conflicting or missing metadata flagged.
- Reported satisfaction kept separate from completed/in-progress/unknown evidence; policies, electives and events preserved without invented course mappings.
- Course-reference linking, tally exclusion and potentially distinct duplicate awards retained for review.
- Editable metadata, course/requirement/count/link controls, add/remove, and explicit confirmation.
- Stateless semantic review validation, correction history, revision identifiers, unresolved flags and recalculated evidence states. Any edit clears confirmation.
- Student-facing review explains unclear details as actionable questions with links to the relevant record. Internal requirement-item/flag counts and revision IDs are hidden. **Use this progress** explains that confirmation accepts planning inputs without certifying degree completion.
- Synthetic representative cohort fixtures, backend/UI regression tests and local setup instructions.
- Sourced Gen Ed starter packs for the 2024, 2025 and 2026 entering cohorts, plus independent CS BS `2025 Fall` and Business `2026 Fall` program packs. Coverage is partial, with explicit manual policies and source locators/content hashes.
- Cohort resolution using reviewed starting-term metadata and scoped requirement signatures. Shared profiles, unsupported years and conflicts remain explicit; program versions resolve separately and rule revisions are returned.
- Versioned catalog/course designations, terms, meetings, sections and explicit bundles, with provenance and credit/link validation.
- Offline JSON validation and atomic immutable publication; source research downloads are ignored and no scraper runs in the application.
- A fixture of 10 fictional courses / 11 course editions, 22 sections and 20 bundles. Source-labeled term/course/section API endpoints, import schemas and CLI documentation are available.
- `POST /api/v1/recommendations`: confirmed-revision validation, scoped direct/attribute matching, candidate explanations/citations, per-match section options, manual items, history exclusions, conditional prerequisite notices and explicit counting limits.
- The frontend now connects upload/review confirmation to semester selection, explained suggestions, paginated course search and a deduplicated optional/required course list. Term changes or audit edits clear selections; canceled requests cannot restore stale results.
- Missing catalog records, nonqualifying/unknown-time offerings, unsupported policies and non-course milestones are explicit. Manual search checks available bundles without claiming requirement coverage or eligibility.
- Credit bounds/target, hard meeting-time/day restrictions and soft time-of-day/compact-day preferences are connected to the selected course list.
- `POST /api/v1/schedules/generate` performs deterministic bounded backtracking over validated linked bundles, with exact credit totals, date-aware conflicts, cross-list alias checks, required/optional choices, stable ranking/deduplication and bounded results.
- Suggested-course restrictions are recomputed server-side with snapshot digest and rule-revision checks. Returned possible matches apply to the chosen bundle and do not imply joint fulfillment.
- The UI displays ranked section lists, supplied meetings/dates, human-readable ranking reasons and no-result/partial-search diagnostics. Any relevant edit clears results and cancels/ignores stale responses.

- Weekly calendars compare two options on a shared scale, filter actual date ranges and explicitly label unknown dates and asynchronous courses. Full section lists and keyboard class details remain available.
- An explicit preferred choice controls print and JSON/ICS downloads; browsing does not change it, and relevant input edits clear it and abort pending exports.
- Stateless server exports regenerate and validate the chosen option against pinned data/rule versions. Downloads omit the reviewed audit/history; ICS converts actual occurrences through Chapel Hill timezone data and never invents asynchronous events.

Verification performed:

- Backend: 176 tests passed. Scheduling cases include an independent small exhaustive oracle, time/date/weekday conflicts, adjacency, linked/standalone labs, decimal and explicit variable credits, required/optional selections, hard restrictions, unknown/asynchronous meetings, cross-listed aliases, deterministic ranking/deduplication, compact/time preferences, bounded search and stale provenance. The installed Starlette emits an httpx test-client deprecation warning; it does not fail tests.
- Frontend: 23 tests passed, including preferences/provenance serialization, validation, schedule details, partial-search/no-results, retry and result invalidation.
- Both supplied original PDFs passed review, resolution, suggestions, sample section scheduling and JSON/ICS exports. The freshman uses suggested DEMO courses; the junior exercises an explicitly chosen manual DEMO course without an invented unmet requirement. No official UNC offerings are implied. See SAMPLE_COVERAGE.md for limits.
- Fictional fixture CLI validation passed. Atomic publication and rejection of changed/invalid imports passed in temporary-directory tests.
- OpenAPI/TypeScript and public JSON schemas regenerated; TypeScript verification and production build passed.

Desktop/mobile Chromium end-to-end checks passed for both synthetic cohort scenarios (4 tests), including keyboard class details, JSON/ICS download contents, print-media isolation, overflow, dependent-result invalidation and impossible-plan feedback. Calendar screenshots were visually inspected. No public deployment or full accessibility/cross-browser audit was performed. The original junior example still uses explicit manual sample-course selection; broader automatic coverage is not implied.

Milestone 7 is in progress: the first bounded manual UNC catalog and public class-search adapters are implemented. A live COMP import validated 115 catalog courses / 22 designations and 341 Spring 2027 section records; 282 section times remain unknown. Raw source caching, offline replay, source-format/count checks, record diffs and access restrictions have 28 regression tests. Outputs are staged, with no change to published application datasets. See [UNC ingestion](UNC_INGESTION.md).

Next: establish verified component/linkage and honors-identity coverage, then validate schedulable real-term imports. The public class-search table lacks those relationships; no bundles were invented. The owner's review/confirmation redesign remains deferred, and broader usability review is still open. Calendar/export behavior and verification details are in [CALENDAR_AND_EXPORT.md](CALENDAR_AND_EXPORT.md). Real UNC ingestion and broader rule exceptions remain separate work. Suggestions/results are planning assistance, not eligibility or graduation approval.
