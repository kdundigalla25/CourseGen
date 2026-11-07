# Requirement-driven course suggestions

Milestone 4 connects upload/review to explained suggestions and course selection. Milestone 5 adds [preferences and schedule generation](SCHEDULING.md). Neither service verifies enrollment eligibility or certifies degree progress. The separate review-UX redesign remains deferred in REVIEW_UX_IDEAS.md.

## Student flow

1. Upload a supported text-based Tracker, correct the extracted progress and choose **Use this progress**.
2. Choose **Semester and course data**. The bundled semester is fictional and is labeled accordingly.
3. Inspect possible courses, the requirements they could help with, published-rule citations and qualifying section alternatives.
4. Add courses to **Courses to consider**, or use course search. Each course starts optional; **Must include** records a preference for the future scheduler.
5. Remove alternatives you do not want. Changing semester data or editing reviewed progress clears the list and cancels stale requests.

The list is populated from reviewed requirements, but suggestions are not automatically selected as a recommended combined load. The preferences form now generates ranked section combinations from the explicit selection. Student data, choices and results remain in tab memory only.

## API and matching

`POST /api/v1/recommendations` takes `reviewed` (the confirmed `ReviewedAudit`), `snapshot_id`, and `term_id`. See `/docs` for the generated contract. The service checks the confirmed revision, resolves applicable Gen Ed/program packs independently, and returns pinned revisions and dataset provenance alongside matches, exclusions and items needing manual interpretation.

Only reviewed **not satisfied** leaf requirements are considered for automatic matching. Satisfied requirements are not reopened; unknown statuses stay manual. Structural headings and in-progress-course administrative summaries do not become extra course requirements. Candidate mappings require an exact, scoped label match to a supported published rule. Major/minor branches prevent one program's rules from leaking into a different branch. Unresolved Gen Ed applicability does not block a separately verified program mapping.

Supported selectors are explicit course options, simple course alternative sets, and edition-specific attributes. Composite rules, elective pools, policies, non-course milestones and unsupported labels stay manual. A requirement or ancestor with unresolved uninterpreted conditions stays manual even if its label matches a known rule. The system does not interpret arbitrary course-like text as a verified fulfillment rule.

Attribute matches use the selected term's course edition and preserve any section-specific scope. Matching bundles must meet sourced minimum-credit selectors and include valid required components. Only bundles with known timed or genuinely asynchronous meetings are selectable through suggestions. Unknown/arranged times, missing catalog details, missing offerings and nonqualifying sections stay visible as informational options with no selectable suggestion. These checks do not detect conflicts between different selected courses; that belongs to the next milestone.

Course search remains available after PDF review even if some requirements cannot be mapped. Manual additions check for a valid known/asynchronous bundle but do not establish requirement coverage. Already completed/in-progress search results display a repeat-eligibility warning. No PDF-free manual mode replaces the primary journey.

## Academic limits

- Completed nonrepeatable courses and courses already in progress are excluded from automatic suggestions. They are not silently used to satisfy an unmet requirement. Low-grade/repeat-policy discrepancies remain visible for manual verification.
- A dataset can explicitly mark a course repeatable; recommendations still warn about repeat-credit and requirement restrictions. Unknown course attempts remain visible as uncertainty.
- Eligibility is always **unverified** or **conditional**, never approved. Prerequisite prose is displayed. A literal reference to an in-progress course can trigger a conditional warning, but this does not parse or prove the prerequisite logic or predict that the student will pass.
- Each match is a potential contribution. Several matches do not imply cumulative fulfillment. Source counting restrictions and grade notes are shown; no progress-maximizing allocation or double-counting solver is implemented.
- A course may have different qualifying section options for different requirements. Those options remain separate; choosing the course does not guarantee every listed match.
- Fictional `DEMO` attributes exercise the flow. They are not evidence that actual UNC offerings exist. Genuine course codes from a published program can appear as unavailable catalog options when absent from the selected dataset; no names or sections are invented for them.

Suggestions sort deterministically by selectable offerings, direct-course versus attribute mapping, then course code. They are not ranked by number of potential requirements, and no fulfilled requirement count is calculated.

## Verification

Backend tests cover direct/scoped mappings, year/program independence, section attributes, historical designations, completion/in-progress exclusions, unknown and repeatable attempts, unknown meeting times, missing offerings, minimum credits, conditional prerequisite warnings, multiple-match restrictions, manual items, deterministic output and stale revisions.

UI tests cover the PDF-confirmation gate, semester choice, selection/deduplication, required flags, manual search and section checks, retry behavior, audit-edit invalidation and stale term-response cancellation. The private local-sample verifier also runs both supplied PDFs through review, resolution and sample-data recommendations, printing only aggregate results. UI tests use a simulated DOM; no visual-browser verification has been performed.
