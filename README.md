# UNC Course Planner

Milestones 1–6 functionality is implemented with partial coverage: Tracker parsing/review, partial sourced rules, validated course imports, explained suggestions, course selection, credit/time preferences and ranked conflict-free section combinations. The review UI remains a working version. Weekly calendar comparison, preferred selection, print and JSON/ICS downloads are available; bundled offerings are clearly fictional.

- [Architecture](docs/ARCHITECTURE.md): system boundaries, curriculum versioning, models, parsing, recommendations, scheduling, API, and deployment.
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md): milestones, dependencies, deliverables, acceptance checks, and review decisions.
- [UNC ingestion](docs/UNC_INGESTION.md): manual COMP catalog collection, section review reports, offline replay and remaining real-term gaps.
- [UNC data sources](docs/DATA_SOURCES.md): initial source research and ingestion validation plan.
- [Curriculum definitions](docs/CURRICULUM_RULES.md) and [course imports](docs/CATALOG_DATA.md): supported packs, limits, API and CLI examples.
- [Course suggestions](docs/RECOMMENDATIONS.md): the reviewed-PDF-to-course-selection flow and matching limits.
- [Schedule generation](docs/SCHEDULING.md): preferences, hard constraints, ranking, limits and diagnostics.
- [Calendar and export](docs/CALENDAR_AND_EXPORT.md): comparison, preferred choice, dates, downloads and browser checks.
- [Review UX ideas](docs/REVIEW_UX_IDEAS.md): deferred redesign questions for the owner to revisit.

The core flow is **upload Tar Heel Tracker → review degree progress → choose suggested courses → set preferences → compare schedules**.

General education requirements depend on the student's starting year at UNC (entering cohort). The requirements listed in their Tar Heel Tracker can identify or corroborate the applicable Gen Ed version. Major and minor requirements have their own applicable versions. Class standing does not select a curriculum.

The disposable parser experiment has been replaced by `backend/app/`. Private reference PDFs and local virtual environments are not committed fixtures. Do not commit private Tracker PDFs or extracted student records.

The supplied `PROJECT_CONTEXT.md` informed these proposals. Implementation follows the reviewed architecture in small milestones.

## Run locally (PowerShell)

Requires Python 3.11+ and Node.js 22+. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e ./backend
npm.cmd --prefix frontend ci
```

Start the API in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```powershell
npm.cmd --prefix frontend run dev
```

Open the local URL printed by Vite (normally `http://127.0.0.1:5173`). Vite forwards `/api` to the local backend. API docs are at `http://127.0.0.1:8000/docs`. Keep the API bound to loopback for local development; this increment is not configured for public hosting.

Choose a Tracker PDF and click **Extract Tracker text**. Review **Starting year & programs**, **Course history**, and **Requirements**. **A few things to double-check** explains unclear details and links directly to the relevant form. Correct/add/remove records and adjust counts as needed, then check the acknowledgment and click **Use this progress**. Any later edit asks you to confirm again. Original page text and page/line evidence remain available for comparison.

The undergraduate career term is retained as starting-term evidence; major/minor requirement terms are independent. Reported satisfaction stays separate from completed/in-progress evidence. Confirmation records corrections and uncertainty, not official fulfillment. After confirming, choose semester data to view possible courses and why they match reviewed unmet requirements. Ambiguous profiles and unsupported requirements remain explicit.

Add suggestions or search results to **Courses to consider**, remove alternatives, and mark required courses. Set credit/time preferences below, then choose **Generate schedules**. Inspect the ranked section lists, meeting times/dates, credit totals and diagnostics. Results enforce hard restrictions but do not verify eligibility or seat availability. Use the weekly calendar and section lists to compare options, then select a preferred option to print or download as JSON/ICS. Calendar dates and asynchronous courses remain explicit.

Changing semester data or reviewed progress clears the course list. Changing course choices or preferences clears generated schedules. Partial searches are labeled and cannot prove that no valid schedule exists. Suggested-course section restrictions are checked again on the server. Restart the API and reload the browser after updating a running version.

Results remain in tab memory; **Clear session** or a page refresh clears them. Uploaded documents and reviewed records are not saved on the server. Scanned PDFs require OCR and are unsupported. If upgrading a running milestone-1 instance, restart the API and reload the browser.

## Verify and update contracts

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe backend/export_openapi.py
.\.venv\Scripts\python.exe backend/export_data_schemas.py
npm.cmd --prefix frontend run generate:api
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

`backend/openapi.json` and `frontend/src/api/schema.d.ts` are generated and committed; regenerate both after backend contract changes. The Python lock captures the tested development environment; dependency changes require updating the lock and rerunning checks. The frontend uses `package-lock.json` with `npm ci` for reproducible installation.

Validate the fictional course fixture with:

```powershell
.\.venv\Scripts\python.exe -m app.ingestion validate data/samples/fictional-demo-v1.json
```

See [course imports](docs/CATALOG_DATA.md) for publication and API examples. The sample contains invented `DEMO` courses and sections, not UNC offerings. Gen Ed definitions cover the 2024, 2025 and 2026 entering cohorts; independent partial program packs cover CS BS `2025 Fall` and Business `2026 Fall`. Exceptions and unsupported mappings remain manual.

See [sample coverage and limits](docs/SAMPLE_COVERAGE.md) and [implementation status](docs/IMPLEMENTATION_STATUS.md). Milestone 7 has started: manual catalog/section source adapters are available, with real sections staged for review. Verified component links and a real-term scheduling release remain next. The owner has deferred further review-UX changes; [the UX note](docs/REVIEW_UX_IDEAS.md) remains open for future ideas.
