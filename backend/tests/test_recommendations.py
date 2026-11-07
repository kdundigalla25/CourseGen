import json

import pytest

from app.audit_review import review
from app.catalog_models import CatalogSnapshot
from app.curriculum import DATA_ROOT, load_rule_packs
from app.models import AuditDraft, AuditRequirement, CourseAttempt, CurriculumSelection, ExtractedPage, ReviewRequest
from app.recommendations import recommend


def snapshot(rename=None):
    data = json.loads((DATA_ROOT / 'samples' / 'fictional-demo-v1.json').read_text(encoding='utf-8'))
    # Synthetic tests can reuse a real code to exercise an exact program selector.
    # The in-memory dataset stays classified fictional and is never published.
    if rename:
        old, new = rename
        for field in ('courses', 'designations', 'sections', 'bundles'):
            for record in data[field]:
                key = 'id' if field == 'courses' else 'course_id'
                if record[key] == old: record[key] = new
    return CatalogSnapshot.model_validate(data)


def reviewed(labels=('Engagement with the Human Past',), year=2026, attempts=None, program=False):
    requirements = [AuditRequirement(id=f'req-{i}', label=label, reported_status='not_satisfied') for i, label in enumerate(labels)]
    if program:
        requirements.insert(0, AuditRequirement(id='major', label='Major: Computer Science (BS)', kind='group', reported_status='not_satisfied'))
        for item in requirements[1:]: item.parent_id = 'major'
    audit = AuditDraft(support='tracker_structure_detected', page_count=1,
        pages=[ExtractedPage(number=1, text='Synthetic source')], issues=[], requirements=requirements, attempts=attempts or [],
        curriculum=CurriculumSelection(starting_year=year, entry_term=f'{year} Fall', reported_catalog_year=f'{year}-{year+1}',
            program_terms={'Computer Science (BS) Major': '2025 Fall'} if program else {}))
    return review(ReviewRequest(original=audit, edited=audit, confirmed=True))


def run(audit=None, data=None):
    return recommend(audit or reviewed(), data or snapshot(), 'sample-spring-2027', load_rule_packs())


def test_known_unmet_attribute_produces_explained_source_scoped_candidate():
    result = run()
    course = result.suggestions[0]
    assert course.course_id == 'DEMO 101' and course.selectable
    assert course.eligibility == 'unverified'
    match = course.matches[0]
    assert match.pack_id == 'ideas-2026-2027' and match.rule_id == 'fc-past'
    assert match.qualifying_bundle_ids == ['bundle-101-a', 'bundle-101-b']
    assert match.sources and '2026-2027' in match.explanation
    assert result.classification == 'fictional' and 'Not official UNC' in result.notice


def test_direct_major_mapping_uses_independent_program_version():
    result = run(reviewed(['COMP 210 (C or Higher)'], year=2024, program=True), snapshot(('DEMO 101', 'COMP 210')))
    course = result.suggestions[0]
    assert course.course_id == 'COMP 210'
    assert course.matches[0].pack_id == 'cs-bs-2025-fall'
    assert any('grade of C' in note for note in course.matches[0].notes)
    assert result.resolution.gen_ed_version == 'ideas-2024-2025'


def test_missing_catalog_candidates_are_visible_but_not_selectable():
    result = run(reviewed(['COMP 210 (C or Higher)'], year=2024, program=True))
    assert result.suggestions[0].availability == 'missing_catalog'
    assert result.suggestions[0].title is None and not result.suggestions[0].selectable
    assert result.manual_requirements[0].reason == 'no_available_candidate'


@pytest.mark.parametrize('status', ['completed', 'in_progress'])
def test_completed_or_current_courses_are_not_automatically_suggested(status):
    audit = reviewed(attempts=[CourseAttempt(id='old', course_id='DEMO 101', title='Prior attempt', term='2025 Fall', credits=3, status=status)])
    result = run(audit)
    assert not result.suggestions
    assert result.excluded_courses[0].reason == status
    assert result.manual_requirements[0].reason == 'no_available_candidate'


def test_completed_low_grade_does_not_silently_satisfy_unmet_requirement():
    attempt = CourseAttempt(id='low', course_id='COMP 210', grade='C-', status='completed', term='2025 Fall', credits=3)
    result = run(reviewed(['COMP 210 (C or Higher)'], year=2024, program=True, attempts=[attempt]), snapshot(('DEMO 101', 'COMP 210')))
    assert not result.suggestions and result.manual_requirements
    assert 'Verify grades' in result.excluded_courses[0].message


def test_unknown_history_and_repeatability_remain_explicit():
    audit = reviewed(attempts=[CourseAttempt(id='unknown', course_id='DEMO 101', status='unknown')])
    assert any('uncertain attempt' in w for w in run(audit).suggestions[0].warnings)
    data = snapshot()
    next(c for c in data.courses if c.id == 'DEMO 101' and c.edition == '2026-2027').repeatable = True
    audit = reviewed(attempts=[CourseAttempt(id='done', course_id='DEMO 101', status='completed', credits=3, term='2025 Fall')])
    assert any('repeatable' in w for w in run(audit, data).suggestions[0].warnings)


def test_section_specific_designation_does_not_qualify_other_sections():
    result = run(reviewed(['Research and Discovery']))
    candidate = next(c for c in result.suggestions if c.course_id == 'DEMO 102')
    assert candidate.matches[0].qualifying_bundle_ids == ['bundle-102-b']
    assert candidate.matches[0].section_options == ['B']


def test_historical_designations_are_not_projected_onto_current_offerings():
    result = run(reviewed(['Aesthetic and Interpretive Analysis']))
    assert not result.suggestions  # DEMO 101 had this designation only in 2024–2025.
    assert result.manual_requirements


def test_multiple_matches_are_not_scored_as_cumulative_fulfillment():
    data = snapshot()
    from app.catalog_models import CourseDesignation
    data.designations.append(CourseDesignation(course_id='DEMO 101', edition='2026-2027', attribute_id='FC-GLOBAL', source_snapshot_id=data.sources[0].id))
    result = run(reviewed(['Engagement with the Human Past', 'Global Understanding and Engagement']), data)
    course = next(c for c in result.suggestions if c.course_id == 'DEMO 101')
    assert len(course.matches) == 2
    assert 'not combined degree credit' in result.counting_notice
    assert any('only one Focus Capacity' in note for match in course.matches for note in match.notes)


def test_noncourse_unknown_and_unmapped_items_stay_manual():
    audit = reviewed(['Campus Life Experience', 'Unrecognized elective pool', 'Engagement with the Human Past'])
    audit.audit.requirements[0].kind = 'non_course'
    audit.audit.requirements[2].reported_status = 'unknown'
    audit = review(ReviewRequest(original=audit.audit, edited=audit.audit, confirmed=True,
        acknowledged_issue_ids=[i.id for i in audit.audit.issues if i.review_required]))
    result = run(audit)
    assert not result.suggestions
    assert {m.reason for m in result.manual_requirements} == {'non_course', 'unmapped', 'status_unknown'}


def test_reported_satisfied_requirements_are_not_reopened():
    audit = reviewed()
    audit.audit.requirements[0].reported_status = 'satisfied'
    audit = review(ReviewRequest(original=audit.audit, edited=audit.audit, confirmed=True))
    assert not run(audit).suggestions


def test_uninterpreted_requirement_conditions_are_not_hidden_by_a_known_label():
    from app.models import Issue
    audit = reviewed()
    audit.audit.issues.append(Issue(id='condition', code='unparsed_requirement_text', message='Unclear extra condition', target_id='req-0', review_required=True))
    audit = review(ReviewRequest(original=audit.audit, edited=audit.audit, confirmed=True, acknowledged_issue_ids=['condition']))
    result = run(audit)
    assert not result.suggestions
    assert result.manual_requirements[0].reason == 'policy_or_elective'


def test_changed_cohort_changes_available_scoped_mapping():
    data = snapshot(('DEMO 104', 'IDST 111L'))
    old = run(reviewed(['First Year Data Lab'], year=2024), data)
    new = run(reviewed(['First Year Data Lab'], year=2026), data)
    assert not old.suggestions
    assert new.suggestions[0].course_id == 'IDST 111L'


def test_unresolved_gened_does_not_prevent_verified_major_candidates():
    audit = reviewed(['COMP 210 (C or Higher)'], year=2024, program=True)
    audit.audit.curriculum.starting_year = audit.audit.curriculum.entry_term = audit.audit.curriculum.reported_catalog_year = None
    audit = review(ReviewRequest(original=audit.audit, edited=audit.audit, confirmed=True))
    result = run(audit, snapshot(('DEMO 101', 'COMP 210')))
    assert result.resolution.gen_ed_version is None and result.suggestions[0].selectable


def test_program_mapping_does_not_leak_into_a_different_major_branch():
    audit = reviewed(['COMP 210 (C or Higher)'], year=2024, program=True)
    audit.audit.requirements[0].label = 'Major: An unsupported program'
    audit = review(ReviewRequest(original=audit.audit, edited=audit.audit, confirmed=True))
    assert not run(audit, snapshot(('DEMO 101', 'COMP 210'))).suggestions


@pytest.mark.parametrize('case', ['missing_sections', 'unknown_meetings', 'insufficient_credits'])
def test_unavailable_or_nonqualifying_offerings_cannot_be_selected(case):
    data = snapshot()
    if case == 'missing_sections':
        data.sections = [s for s in data.sections if s.course_id != 'DEMO 101']
        data.bundles = [b for b in data.bundles if b.course_id != 'DEMO 101']
    elif case == 'unknown_meetings':
        from app.models import Meeting
        for section in data.sections:
            if section.course_id == 'DEMO 101': section.meetings = [Meeting(kind='unknown')]
    result = run(reviewed(['Ways of Knowing']) if case == 'insufficient_credits' else reviewed(), data)
    course = result.suggestions[0]
    assert not course.selectable
    assert course.availability == {'missing_sections': 'not_offered', 'unknown_meetings': 'unknown_meetings', 'insufficient_credits': 'no_qualifying_sections'}[case]


def test_in_progress_prerequisite_is_conditional_not_verified_eligibility():
    data = snapshot()
    next(c for c in data.courses if c.id == 'DEMO 101' and c.edition == '2026-2027').prerequisite_text = 'Prerequisite: COMP 110.'
    audit = reviewed(attempts=[CourseAttempt(id='current', course_id='COMP 110', term='2026 Fall', credits=3, status='in_progress')])
    candidate = run(audit, data).suggestions[0]
    assert candidate.eligibility == 'conditional'
    assert any('in progress' in warning for warning in candidate.warnings)


def test_recommendations_are_deterministic_and_reject_stale_review(client):
    audit = reviewed()
    assert run(audit).model_dump() == run(audit).model_dump()
    body = dict(reviewed=audit.model_dump(mode='json'), snapshot_id='fictional-demo-v1', term_id='sample-spring-2027')
    response = client.post('/api/v1/recommendations', json=body)
    assert response.status_code == 200 and response.json()['audit_revision'] == audit.revision
    body['reviewed']['audit']['requirements'][0]['label'] = 'Changed after confirmation'
    assert client.post('/api/v1/recommendations', json=body).json()['error']['code'] == 'stale_review'
    body['reviewed'] = audit.model_dump(mode='json')
    body['term_id'] = 'unknown'
    assert client.post('/api/v1/recommendations', json=body).status_code == 404
