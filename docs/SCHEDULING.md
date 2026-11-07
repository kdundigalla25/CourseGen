# Preferences and deterministic section scheduling

Milestone 5 adds credit/time preferences and ranked section combinations to the reviewed-PDF-to-course-selection flow. Milestone 6 adds weekly calendar comparison, preferred-schedule selection, print and JSON/ICS exports while retaining accessible section lists. See [calendar and export](CALENDAR_AND_EXPORT.md). The review-UX redesign remains deferred.

## Student flow

Upload and confirm a supported Tracker, select semester data, then add suggested or searched courses. Mark courses that every result must include. In the preferences form choose:

- Minimum/maximum credits (hard limits) and a target within that range (ranking preference).
- Earliest fixed-meeting start, latest fixed-meeting end and days to avoid (hard restrictions).
- Preferred morning/afternoon and fewer fixed-meeting days (soft preferences).
- At most 5, 10 or 20 results.

Generate schedules to inspect course/section combinations, credits, days, times, supplied date ranges and preference explanations. Optional courses may be omitted; at least one course is required in a returned schedule. Changes to preferences, course choices, reviewed progress or semester data invalidate results and cancel/ignore stale client requests. Nothing is saved outside the current tab.

## API and provenance

`POST /api/v1/schedules/generate` accepts a confirmed `ReviewedAudit`, snapshot/term IDs, selected courses with required/optional flags, preferences, result limit and deterministic node budget. See `/docs` for the generated schema.

Suggested selections include their intended `requirement_ids`, rule revisions and `expected_snapshot_digest` from the recommendation response. The server recomputes current matches, checks the digest/revisions and restricts bundles accordingly; it does not accept a client-authored list of qualifying section IDs. A course with several possible matches may use a bundle qualifying for at least one requested match. The result identifies which matches actually apply to that bundle without claiming cumulative fulfillment.

Manual selections assert no verified requirement coverage. They still undergo course, term, component, credit and conflict validation. If provenance is supplied it must agree with current data. Results record the audit revision, source snapshot/digest, active rule revisions, timezone and sample/public notice. Eligibility and seat availability remain unverified.

## Search and hard constraints

1. Use only explicit validated bundles for the selected term/course edition. Exactly one bundle is selected for each included course; required courses cannot be skipped.
2. Filter bundles against allowed meeting days/times, unknown-time policy, internal component conflicts and duplicate physical cross-listed sections.
3. Order required courses first, then those with fewer choices, with stable course/bundle-ID ties.
4. Backtrack with optional-course skip branches. Prune when required remaining credits exceed the maximum or the remaining available credits cannot reach the minimum. Decimal arithmetic preserves credit totals.
5. Reject cross-course meeting conflicts and shared physical cross-list groups. Count each chosen bundle's credit value once; required lab components do not duplicate course credit. A separate credit-bearing lab course retains its credits.
6. Keep only the best bounded result set, deduplicate by sorted section IDs and rank deterministically. No hard restriction is relaxed automatically.

Timed meetings conflict on a common weekday when time intervals intersect (`startA < endB && startB < endA`) and their applicable dates share an occurrence of that weekday. Adjacent meetings do not conflict. Supplied date ranges are honored; missing dates use term dates, or conservatively assume concurrency when no bounds exist. Meetings use Chapel Hill local wall-clock time (`America/New_York`).

Unknown and arranged times are excluded. True asynchronous meetings impose no fixed-time/day restriction. Cross-list detection uses explicit `crosslist_group_id` values identifying physical class aliases; it does not infer equivalence from titles or codes. Source adapters must supply those IDs accurately for complete coverage.

Variable-credit courses use explicit imported bundle values. The engine does not invent a credit amount from a course's range; additional credit choices need validated offering data. This first version does not provide a per-course arbitrary-credit editor.

## Ranking configuration

All weights live in `backend/app/scheduling.py::WEIGHTS`. Lower penalty ranks first:

| Component | Weight |
| --- | --- |
| Absolute distance from credit target | 100 per credit |
| Fixed minutes outside preferred morning/afternoon | 1/30 per minute |
| Gaps in the shared-weekday meeting template | 1/15 per minute |
| Distinct fixed-meeting weekdays, when compact days requested | 20 per day |

Morning ends at noon; afternoon includes noon onward. Gap estimates use adjacent meetings with overlapping applicable dates. Compact-day scoring counts weekdays across the term, including online synchronous meetings; it is not a travel-time estimate or a week-by-week attendance calculation. Date-restricted courses remain explicitly labeled in results. Ties use sorted section IDs, not randomization. Matching more potential requirements does not improve the score.

## Bounds and diagnostics

Limits: 1–12 selected courses, 0–30 credit bounds, 1–20 returned schedules and up to 200,000 search nodes (100,000 default). Proven required-pair conflict diagnostics examine at most 10,000 pairs before falling back to the bounded general search. These limits are application guards, not a public-deployment resource sandbox.

`search_complete=false` means the node limit stopped enumeration. Returned schedules still satisfy hard constraints, but the ranking is only the best encountered so far. Empty partial results do not prove impossibility. The UI labels this distinction explicitly.

Complete no-results responses explain proven unavailable required courses, impossible credit bounds, mutually conflicting required courses, or general incompatibility where no more specific proof was obtained. Filtering reports show the first rejection reason for each bundle; fixing one restriction may reveal another. Suggestions are offered as possible changes, never applied without the student editing their preferences.

## Verification

Engine tests cover exhaustive-oracle agreement on small cases, overlap/adjacency, weekday/date intersection, required versus optional choices, linked and separate labs, exact fractional credits, explicit variable credits, unknown/asynchronous meetings, hard restrictions, compact/time preferences, cross-listed aliases, deterministic ordering/deduplication, search truncation, stale provenance and section-specific requirement restrictions.

UI tests cover preference serialization, validation, required flags/provenance, results and diagnostics, partial-search wording, request errors/retry and invalidation after edits. The optional private sample verifier exercises suggested scheduling for the freshman sample and an explicitly selected manual DEMO course for the junior sample, whose remaining automatically mapped coursework does not require a new suggested class. It never fabricates an unmet requirement to manufacture a recommendation.

Calendar comparison, preferred selection, print and JSON/ICS exports are implemented; see [calendar and export](CALENDAR_AND_EXPORT.md). Desktop/mobile Chromium flows and calendar screenshots have been checked. No public deployment has been performed. Broader source coverage, enrollment/prerequisite verification, user accounts, live offerings and public-hosting safeguards remain separate work.
