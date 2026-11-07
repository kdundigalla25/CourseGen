# UNC source adapters: first validated subject

The first milestone-7 increment provides a manual, bounded public-source collector, a catalog parser, and a review-only section parser. It does not yet provide a real-term scheduling release. Existing application datasets remain unchanged.

## Verified sources and coverage

On November 7, 2026, the canonical [COMP catalog](https://catalog.unc.edu/courses/comp/) returned a complete 2026–2027 subject page with 115 course blocks and 22 course-level IDEAs designations. The parser preserves course identifiers, edition, titles, descriptions, fixed/fractional/variable credit ranges, requisite prose, repeatability and raw designation codes. It checks the page edition and subject, every course block, duplicate identifiers, credit syntax and designation syntax. It does not infer honors identifiers from a base course or convert prerequisite prose into verified eligibility.

A normal public [UNC class-search](https://reports.unc.edu/class-search/) form submission for `COMP`, `2027 Spring` returned 47 courses / 341 sections. The parser checks both displayed totals against expanded table rowspans. Of these sections, 59 have fixed meeting patterns and 282 have an unspecified schedule. An unspecified schedule remains **unknown**, not asynchronous. Dates and wall-clock times are parsed exactly; `TTH` means Tuesday and Thursday. Course identifiers `COMP 283H`, `COMP 380H` and `COMP 530H` appear in the search results but not as independent catalog blocks; the report retains them as gaps instead of inventing catalog equivalence.

The table supplies class/section identifiers, course codes, term, hours, dates, schedules, instruction labels, cross-list prose and a seat snapshot. It does **not** supply component types, required component links, physical cross-list equivalence, rooms or instructors. No schedulable bundles are created. Instruction labels and cross-list prose are preserved in the report; section component/linkage/modality remain unknown where they cannot be independently established. Seat counts are not imported into the planner or treated as live availability.

The public normal search is server-rendered HTML with a regular POST form and CSRF cookie/token. This is an observed website interface, not a documented public API contract. No private endpoint, sign-in or challenge was used. No supported export/feed was identified in these pages; that is not proof none exists.

## Access and collection policy

[Catalog robots guidance](https://catalog.unc.edu/robots.txt) allows the course-subject path while disallowing paths including `/archives/`, `/search/`, `/ribbit/` and `/js/`. The adapter's URL allowlist excludes these paths. The reports host's robots endpoint returned 404 during this investigation. Robots guidance is an access signal, not a grant of recurring automation rights; no blanket recurring-collection permission or complete review of university terms has been established. This increment performs explicit manual runs only, without a crawler or scheduled refresh.

The collector uses HTTPS on the two canonical hosts, identifies itself, checks available robots instructions, spaces requests by at least one second and honors larger crawl-delay/request-rate guidance. It retries transient transport/server failures at most twice with backoff. Redirects, authentication failures, denials and rate limits stop collection. Responses are bounded to 10 MB with a 25-second request timeout. There is no proxy rotation, browser bypass or authentication fallback.

Raw public responses are content-addressed in ignored `data/source-cache/unc-import/`. Each successful request receipt records URL, retrieval timestamp and SHA256. POST cache identity also includes the explicit subject/term query. Cache reads verify the byte hash. A normal run reuses cached subject/results responses; `--refresh` explicitly retrieves new data. Search-form GETs are fresh to obtain a matching public CSRF cookie. `--offline` makes no network requests. Cookies stay in the collector process; raw form HTML may contain public CSRF tokens and remains ignored cache, never a committed test fixture.

## Run and review

Install dependencies using the updated `backend/requirements-lock.txt`. From the project root:

```powershell
# Collect one explicit subject/edition and inspect one public term.
.\.venv\Scripts\python.exe -m app.unc_ingestion --subject COMP --edition 2026-2027 --term "2027 Spring"

# Replay the same source bytes, timestamps and query without any network calls.
.\.venv\Scripts\python.exe -m app.unc_ingestion --subject COMP --edition 2026-2027 --term "2027 Spring" --offline

# Explicit refresh; optionally compare against a previous report's actual path.
.\.venv\Scripts\python.exe -m app.unc_ingestion --subject COMP --edition 2026-2027 --term "2027 Spring" --refresh --compare-report data/staging/reports/PREVIOUS-REPORT.json
```

Omit `--term` to collect only catalog definitions. `--cache` and `--directory` select local destinations. The source edition must match the requested edition; the adapter cannot retrieve historical editions through disallowed archive paths. Other subjects are supported by syntax but have not been manually reconciled; changes in fields fail validation rather than silently producing partial records.

Outputs:

- `data/staging/catalogs/`: complete validated `CatalogSnapshot` JSON containing catalog definitions only, with no terms, sections or bundles. Snapshot IDs include source bytes and retrieval context, making cached replay stable while refreshed receipts get their own immutable revision.
- `data/staging/reports/`: source/query provenance, catalog definition fingerprints, all parsed offering rows, unknown-time counts, missing catalog identifiers and explicit limitations. Optional comparison reports added/removed/changed course and section records, ignoring retrieval-ID-only changes. Reports from a different subject, edition or term cannot be compared.

All requested responses must parse before staging. Staging does not alter `data/published/`, which remains the application's import boundary. Existing immutable/atomic publication protections apply to staged catalog JSON too. Failed collection/validation cannot replace a published dataset. To publish a reviewed **catalog-only** file, use the existing `python -m app.ingestion publish ACTUAL-CATALOG-PATH` command. It introduces no selectable semester. Section review reports are deliberately not accepted as scheduling datasets.

## Verification and remaining release gate

28 adapter tests cover catalog credits/designations/edition guards, changed HTML, duplicate identifiers, truncated documents, rowspans, result counts, weekdays/dates, unknown times, robots/access restrictions, response limits, verified cache/offline replay, failure retention, normal form submission and record diffs. Fixtures contain minimal public structural excerpts with synthetic descriptions/requisites and no tokens or student records. Fixture origins are the two canonical pages above; they are not fabricated official offerings.

The full COMP source parsed successfully and replayed offline. Representative checks compared COMP 110's three sections and COMP 116 against the public table, including identifiers, credits, dates, MWF and TTH times; catalog checks included COMP 110 / 210 / 380 titles, credits, requisite presence and FC-QUANT / FC-VALUES attributes. These checks do not establish completeness beyond this subject/query or validate missing component relationships.

Before a real-term release: identify a permitted source/export with explicit component relationships and independently verify standalone sections, cross-lists, lecture/lab combinations, asynchronous and date-restricted cases. Resolve honors catalog identities and section/topic-specific designations. Validate broader subjects, source policy and refresh expectations, then build and reconcile schedulable bundles and run a real-term end-to-end plan. The fictional fixture remains the only bundled schedulable semester until those checks pass.
