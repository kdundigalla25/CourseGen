# Course and offering imports

The current importer accepts versioned JSON, performs validation and publishes immutable local snapshots. The separate [UNC subject adapters](UNC_INGESTION.md) now collect and stage catalog definitions in this contract. Their section output remains a review report because the public table lacks verified component links; it cannot yet provide schedulable bundles.

## Try the fictional dataset

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m app.ingestion validate data/samples/fictional-demo-v1.json
.\.venv\Scripts\python.exe -m app.ingestion publish data/samples/fictional-demo-v1.json
```

Validation prints record counts and a normalized-content SHA256. Publication writes to ignored `data/published/` by default; `--directory` selects another local destination. The sample remains discoverable without publication from `data/samples/`. Publishing an identical snapshot again is harmless. Changed data require a new snapshot ID.

The fixture contains **10 fictional courses**, 11 course editions, 22 sections and 20 explicit section bundles. Every course uses the invented `DEMO` subject. All names, meeting dates and offerings are fictional, not UNC schedules. Cases include conflicting and alternate meetings, lecture/required-lab pairs, a separate credit-bearing lab, evening, asynchronous, unknown-time, date-restricted and variable-credit offerings. Impossible scheduling preferences can be exercised against this fixture once the solver exists.

Reproduce it with `python backend/build_sample_data.py` using the project environment. It also demonstrates a course whose attribute differs across catalog editions and a designation attached only to one section. The fixture's timestamp describes authored sample data, not an official refresh.

## Contract

[Catalog snapshot JSON schema](../data/schemas/catalog-snapshot.schema.json) is generated from the backend models. `data/samples/fictional-demo-v1.json` is a complete example.

| Collection | Purpose |
| --- | --- |
| `sources` | Source IDs, fictional/public classification, edition, retrieval/provenance and optional content hash/adapter version |
| `courses` | Stable course IDs with edition-specific title, description, credit range and prerequisite text |
| `designations` | Attributes tied to a course edition, optionally narrowed to a term and section |
| `terms` | Actual source IDs, name, catalog edition, optional dates and campus timezone |
| `sections` | Term-scoped IDs, meetings, modality, components, explicit credit contribution, known linkage status and required component IDs |
| `bundles` | Explicit valid combinations of sections for one course and term, with total credits |

Public sources need a valid URL and timezone-aware retrieval timestamp. A snapshot cannot mix fictional and public sources. Every record references a known source; each offering resolves to a known course edition. Duplicate IDs, bad dates/times, invalid relationships and incompatible bundle credits are rejected.

Bundle credit totals must equal explicit section contributions and fall within the course's credit range. A lab included in a four-credit course can contribute zero additional credits; a separately credit-bearing lab retains its own course and credit value. Component linkage must be explicitly verified or known not to be required before a bundle is considered valid. Missing linkage is not interpreted as permission to pair arbitrary sections.

Timed meetings require weekday (Monday = 0), start/end minutes and a positive interval. Optional date ranges require both dates and must fit within known term dates. Asynchronous, arranged and unknown meetings remain explicit; no times are invented. Unknown-time bundles are valid imported records, not a claim of conflict-free schedulability. The scheduling engine must apply its documented unknown-time policy later.

Course search may return a course because **one** section has an attribute. The returned designation keeps that section ID; later recommendation/scheduling code must not apply it to every section. Catalog-only historical editions can exist without any target-term offerings.

## Read API

Start the API and inspect `/docs`:

- `GET /api/v1/terms`: available terms, snapshot IDs, sample/public labels and sources.
- `GET /api/v1/courses?snapshot_id=fictional-demo-v1&term_id=sample-spring-2027`: target-term courses. Optional `q`, `attribute_id`, `offset`, and `limit` (1–100).
- `GET /api/v1/courses/DEMO%20103/sections?snapshot_id=fictional-demo-v1&term_id=sample-spring-2027`: sections and explicit bundles.

Snapshot selection is required for course queries so data from unrelated imports are not mixed. Attribute queries preserve edition and section scope. Unknown IDs return 404; invalid local datasets return a safe 503 rather than partial success. There is no publicly exposed write/import endpoint.

## Publication guarantees and limits

Validate the complete import before publication. Write and flush a temporary file in the destination, then atomically link the complete file into place without overwriting an existing snapshot. Clean up the temporary file on success or failure. An invalid import or changed snapshot ID collision cannot replace the last valid data. Publication requires a filesystem supporting same-directory hard links; unsupported filesystems fail explicitly rather than using a partial-file fallback.

Files in `data/samples/` and `data/published/` are validated again when loaded. Conflicting snapshot IDs are rejected. Do not modify published files manually; create a new version. CLI imports are bounded to 10 MB. Use JSON for nested meetings and links; CSV normalization can be added if a real source/export requires it.

Recommendations and scheduling now use this data for potential matches and valid section combinations. Cross-listed physical aliases can be identified with `Section.crosslist_group_id`. Enrollment, seat freshness and verified prerequisite eligibility remain unimplemented. Prerequisite prose is descriptive until structured constraints exist.
