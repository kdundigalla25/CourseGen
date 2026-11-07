import type { components } from './api/schema';

export const draftFixture: components['schemas']['AuditDraft'] = {
  schema_version: '1', parser_version: 'tracker-0.2', support: 'tracker_structure_detected', review_state: 'needs_review',
  page_count: 1, pages: [{ number: 1, text: 'Synthetic Tracker text' }],
  curriculum: { starting_year: 2026, entry_term: '2026 Fall', reported_catalog_year: '2026-2027', method: 'unresolved', program_terms: {} },
  attempts: [], requirements: [{ id: 'req-1', label: 'Engagement with the Human Past', reported_status: 'not_satisfied', completion: 'unknown', kind: 'unknown', needs_review: false }], issues: [],
};
export const reviewedFixture: components['schemas']['ReviewedAudit'] = {
  review_state: 'confirmed', revision: 'fixture-revision', audit: draftFixture, changes: [], acknowledged_issue_ids: [], unresolved_issues: [],
};
const sources: components['schemas']['SourceSnapshot'][] = [{ id: 'fictional', classification: 'fictional', edition: '2026-2027' }];
export const termsFixture: components['schemas']['AvailableTerm'][] = [{
  snapshot_id: 'fictional-demo-v1', classification: 'fictional', notice: 'Fictional sample data. Not official UNC offerings.', sources,
  term: { id: 'sample-spring-2027', name: 'Fictional Spring 2027', catalog_edition: '2026-2027', timezone: 'America/New_York' },
}];
export const suggestionsFixture: components['schemas']['RecommendationResult'] = {
  audit_revision: reviewedFixture.revision, snapshot_id: 'fictional-demo-v1', snapshot_digest: 'a'.repeat(64), term_id: 'sample-spring-2027', classification: 'fictional', notice: termsFixture[0].notice, sources,
  resolution: { state: 'selected', gen_ed_version: 'ideas-2026-2027', method: 'metadata', candidate_versions: ['ideas-2026-2027'], unsupported_cohort_years: [], programs: [], evidence: [], warnings: [], rule_revisions: { 'ideas-2026-2027': '1' }, coverage: 'partial' },
  suggestions: [{ course_id: 'DEMO 101', edition: '2026-2027', title: 'Fictional History', credits_min: 3, credits_max: 3, availability: 'available', selectable: true, eligibility: 'unverified', prerequisite_text: null, warnings: ['Check prerequisites.'], matches: [{
    requirement_id: 'req-1', label: 'Engagement with the Human Past', pack_id: 'ideas-2026-2027', rule_id: 'fc-past', match_type: 'attribute', explanation: 'The sample edition records FC-PAST.', qualifying_bundle_ids: ['bundle-101-a'], section_options: ['A'], audit_evidence: [], notes: ['A course counts toward only one Focus Capacity.'],
    sources: [{ id: 'rule', url: 'https://catalog.unc.edu/undergraduate/ideas-in-action/', edition: '2026-2027', locator: 'Requirements', verified_on: '2026-11-07', content_sha256: '0'.repeat(64) }],
  }] }], manual_requirements: [{ requirement_id: 'campus', label: 'Campus Life Experience', reason: 'non_course', message: 'Complete the activity separately; it is not a course.', amounts: [], evidence: [] }], excluded_courses: [],
  counting_notice: 'Matches are possibilities, not combined degree credit.', warnings: [],
};
export const catalogFixture: components['schemas']['CourseSearchResult'] = {
  snapshot_id: 'fictional-demo-v1', classification: 'fictional', notice: termsFixture[0].notice, total: 1, offset: 0, limit: 20,
  courses: [{ course: { id: 'DEMO 101', title: 'Fictional History', credits_min: 3, credits_max: 3, source_snapshot_id: 'fictional', edition: '2026-2027', repeatable: false }, designations: [] }],
};
export const sectionsFixture: components['schemas']['SectionOptions'] = {
  snapshot_id: 'fictional-demo-v1', classification: 'fictional', notice: termsFixture[0].notice, course_id: 'DEMO 101', term_id: 'sample-spring-2027', sources,
  sections: [{ id: 'section-a', term_id: 'sample-spring-2027', course_id: 'DEMO 101', number: 'A', source_snapshot_id: 'fictional', component: 'lecture', modality: 'in_person', credit_value: 3, linkage_status: 'not_required', meetings: [{ kind: 'timed', weekday: 0, start_minute: 540, end_minute: 590 }] }],
  bundles: [{ id: 'bundle-101-a', term_id: 'sample-spring-2027', course_id: 'DEMO 101', section_ids: ['section-a'], credits: 3, source_snapshot_id: 'fictional' }],
};

export const jsonResponse = (data: unknown, ok = true) => Promise.resolve({ ok, json: async () => data } as Response);
