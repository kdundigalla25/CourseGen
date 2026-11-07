# UNC data sources and ingestion plan

Initial research: November 6, 2026; manual source verification updated November 7. Published catalog definitions were read for the partial rule packs. A bounded manual COMP catalog adapter and review-only public section adapter are implemented; see [UNC ingestion](UNC_INGESTION.md). Verified component links, schedulable real-term integration, recurring automation permission and complete policy coverage remain open.

## Observed sources

| Source | Intended use | Observed status and limits |
| --- | --- | --- |
| [UNC catalog archives](https://catalog.unc.edu/archives/) | Historical Gen Ed and program versions | Canonical archive page retrieved. Public 2024–2025 and 2025–2026 catalog PDFs downloaded locally for manual verification; raw downloads are ignored research cache. |
| [IDEAs in Action catalog entry](https://unc-public.courseleaf.com/undergraduate/ideas-in-action/) | Published curriculum applicability and Gen Ed categories | Search surfaced a UNC-branded CourseLeaf entry that explicitly distinguishes entering cohorts and archived rules. Verify its relationship to the canonical catalog before configuring an ingestion source. |
| [Canonical Gen Ed entry](https://catalog.unc.edu/undergraduate/ideas-in-action/) | Current curriculum definitions | Earlier web retrieval failures were transient. Canonical HTML was retrieved directly and verified as 2026–2027; rule-pack sources record a content hash and section locator. |
| [Courses of Instruction](https://unc-public.courseleaf.com/courses/) | Subject index and course discovery | Search surfaced a 2026–2027 catalog index. Course-level field coverage and canonical hosting require verification. |
| [Canonical COMP listing](https://catalog.unc.edu/courses/comp/) | Representative catalog adapter target | Retrieved and parsed 2026-2027 canonical HTML: 115 course blocks / 22 IDEAs designations. Strict selectors and edition guards are tested. |
| [UNC–Chapel Hill Class Search](https://reports.unc.edu/class-search/) | Candidate source for semester-specific sections | Public page retrieved successfully; exposes term, subject and catalog-number filters. Normal public form POST inspected for COMP / 2027 Spring: 47 courses / 341 sections. Counts/rowspans parse completely; component links are absent and remain unverified. |

Partial category/candidate definitions are now sourced from [2024–2025 PDF pp. 1195–1197](https://catalog.unc.edu/pdf/2024-25-ugrad.pdf), [2025–2026 PDF pp. 634–636](https://catalog.unc.edu/pdf/2025-26-ugrad.pdf), and the current canonical Gen Ed entry. The 2025 and 2026 first-year/interdisciplinary profiles overlap, so those requirement names alone cannot identify an exact starting cohort. See [rule coverage](CURRICULUM_RULES.md) for conservative resolution and unimplemented policies.

The independent CS BS mapping uses 2025–2026 catalog PDF p. 282. Business `2026 Fall` mapping uses the [canonical 2026–2027 major page](https://catalog.unc.edu/undergraduate/programs-study/business-administration-major-bsba/), including its admission-year applicability statement. The canonical path includes `/undergraduate/`; a preliminary URL without that prefix returned 404. Current search snippets can show older program content, so source edition was checked directly rather than inferred from search-result freshness.

Manual retrieval verifies the cited published material, not permission for recurring automated collection. Large source PDFs and HTML are excluded from version control. Runtime services load committed rule JSON offline. The first adapters and their access/field coverage limits are documented in UNC_INGESTION.md. Broader collection still requires the checks below.

The public class-search page establishes a promising offering source, not a supported public API. This research neither establishes that a public API exists nor proves that none exists.

## Validation work before collection

1. Follow canonical UNC links and verify hosts, redirects, applicable terms of use, robots guidance, and any published access/export instructions. Robots guidance alone does not grant permission.
2. Check for supported feeds/exports first. If permitted, inspect a normal public search's requests to determine whether HTML, structured responses, or downloadable files supply results. Record supported versus undocumented interfaces explicitly.
3. Verify one subject and term manually, including pagination and complete result counts. Identify stable course, section, cross-list, and term identifiers from source records.
4. Check sample lectures, labs, recitations, asynchronous sections, TBA records, variable credits, date-restricted meetings, and linked components. Record fields absent from the source instead of inventing them.
5. Establish how designations relate to course editions and any section/topic-specific exceptions. Verify a historical designation against an archived source before using it for old coursework.
6. Compare at least two Gen Ed editions and document starting-cohort applicability, category changes, exemptions, aliases and reuse restrictions. Define verified requirement signatures for identifying a curriculum from a Tracker when starting-year metadata is missing; record where several cohorts are indistinguishable. Review major mappings independently.
7. Choose and document allowed request rates, refresh cadence, cache policy, retries, and source failure behavior. No precise freshness promise until this is known.
8. Produce a source-adapter report: URLs, access findings, example redacted/public records, field coverage, completeness checks, parsing contract, and unresolved gaps.

Do not bypass sign-in, CAPTCHA, rate limits or access restrictions. If required fields are unavailable through a reliable permitted route, keep the documented import path and identify which product claims cannot be supported.

## Snapshot publication and freshness

Each published dataset records source URLs, retrieval time, effective catalog edition/target term, adapter version, schema version, validation results and content hash. Public source material may be retained to reproduce imports; student PDFs are not ingestion snapshots.

Publish separate catalog and term-offering snapshots. Requirement packs reference their own editions and sources. A source refresh does not mutate an older rule pack or a plan's pinned dataset. Replanning against newer data is explicit and reports removed/changed sections.

Initial refreshes are manual CLI runs. Failed, incomplete, or structurally changed source responses retain the last validated dataset and mark refresh failure. Display retrieval time; never imply real-time seat availability. If no usable dataset exists for a term, disable generation for that term and explain how an import can provide one.

## Import fallback

Use versioned JSON as the canonical nested representation for meetings and component relationships. CSV import may use separate course, section, meeting and linkage tables with documented keys. Both normalize into the same models as scraper output and receive the same validation. Sample data remain clearly fictional and cannot be published as official UNC data.
