from datetime import date
from itertools import product

import pytest
from pydantic import ValidationError

from app.audit_review import InvalidReview
from app.catalog_models import CatalogSnapshot, CourseDesignation, Term
from app.curriculum import load_rule_packs
from app.models import Meeting
from app.recommendations import recommend
from app.scheduling import generate_schedules, meetings_conflict
from app.scheduling_models import SchedulePreferences, ScheduleRequest, SchedulingSelection
from test_recommendations import reviewed, snapshot


def request(codes=('DEMO 101',), *, required=True, **fields):
    return ScheduleRequest(reviewed=reviewed(), snapshot_id='fictional-demo-v1', term_id='sample-spring-2027',
        selections=[SchedulingSelection(course_id=code, required=required) for code in codes],
        preferences=fields.pop('preferences', SchedulePreferences(minimum_credits=3, target_credits=3, maximum_credits=18)), **fields)


def run(req=None, data=None):
    return generate_schedules(req or request(), data or snapshot(), load_rule_packs())


def meeting(start=540, end=590, day=0, **fields):
    return Meeting(kind='timed', weekday=day, start_minute=start, end_minute=end, **fields)


@pytest.mark.parametrize(('a', 'b', 'conflict'), [
    (meeting(), meeting(580, 620), True), (meeting(), meeting(590, 640), False),
    (meeting(), meeting(day=1), False), (meeting(), Meeting(kind='asynchronous'), False),
    (meeting(start_date=date(2027,1,11),end_date=date(2027,1,17)), meeting(start_date=date(2027,1,18),end_date=date(2027,1,24)), False),
    (meeting(start_date=date(2027,1,11),end_date=date(2027,1,18)), meeting(start_date=date(2027,1,18),end_date=date(2027,1,25)), True),
    (meeting(start_date=date(2027,1,11),end_date=date(2027,1,14)), meeting(start_date=date(2027,1,12),end_date=date(2027,1,18)), False),
])
def test_interval_weekday_and_actual_date_conflicts(a, b, conflict):
    term = Term(id='test', name='Test', catalog_edition='test')
    assert meetings_conflict(a, b, term) is conflict


def test_small_exhaustive_oracle_agrees_with_feasible_schedule_set():
    data = snapshot()
    req = request(('DEMO 101','DEMO 102','DEMO 103'), result_limit=20,
        preferences=SchedulePreferences(minimum_credits=6, target_credits=10, maximum_credits=10))
    req.selections[-1].required = False
    sections = {s.id:s for s in data.sections}
    choices = [[b for b in data.bundles if b.course_id == s.course_id] + ([] if s.required else [None]) for s in req.selections]
    expected = set()
    # Independent brute-force oracle for this fixture's fixed, full-term meetings.
    for combination in product(*choices):
        bundles = [b for b in combination if b]
        credits = sum(b.credits for b in bundles)
        times = [m for b in bundles for key in b.section_ids for m in sections[key].meetings if m.kind == 'timed']
        valid = 6 <= credits <= 10
        for i, a in enumerate(times):
            for b in times[i+1:]:
                if a.weekday == b.weekday and max(a.start_minute,b.start_minute) < min(a.end_minute,b.end_minute): valid = False
        if valid: expected.add(tuple(sorted(key for b in bundles for key in b.section_ids)))
    result = run(req, data)
    actual = {tuple(sorted(section.id for c in schedule.courses for section in c.sections)) for schedule in result.schedules}
    assert result.search_complete and actual == expected and expected


def test_required_components_and_separate_lab_credit_are_preserved():
    result = run(request(('DEMO 103','DEMO 104'), preferences=SchedulePreferences(minimum_credits=5,target_credits=5,maximum_credits=5)))
    assert result.schedules
    for schedule in result.schedules:
        assert schedule.total_credits == 5
        linked = next(c for c in schedule.courses if c.course_id == 'DEMO 103')
        assert len(linked.sections) == 2 and linked.credits == 4
        assert next(c for c in schedule.courses if c.course_id == 'DEMO 104').credits == 1
        assert set(linked.sections[0].required_component_ids) <= {s.id for s in linked.sections}


def test_optional_courses_credit_target_and_deduplication_are_deterministic():
    req = request(('DEMO 101','DEMO 102'), required=False, result_limit=20,
                  preferences=SchedulePreferences(minimum_credits=3,target_credits=6,maximum_credits=6))
    first, second = run(req), run(req)
    assert first.model_dump() == second.model_dump()
    assert first.schedules[0].total_credits == 6
    assert any(s.total_credits == 3 for s in first.schedules)
    assert len({s.id for s in first.schedules}) == len(first.schedules)
    assert [s.score for s in first.schedules] == sorted(s.score for s in first.schedules)


@pytest.mark.parametrize(('preferences','reason'), [
    (dict(avoided_days=list(range(7))), 'avoided_day'),
    (dict(earliest_start=1000, latest_end=1100), 'time_window'),
])
def test_hard_constraints_are_never_relaxed(preferences, reason):
    result = run(request(preferences=SchedulePreferences(minimum_credits=3,target_credits=3,maximum_credits=3,**preferences)))
    assert not result.schedules and result.search_complete
    assert result.filtered_courses[0].rejected_reasons[reason] == 2
    assert any(d.code == 'required_course_unavailable' for d in result.diagnostics)


def test_asynchronous_sections_work_with_all_days_avoided_and_unknown_times_are_excluded():
    prefs = SchedulePreferences(minimum_credits=3,target_credits=3,maximum_credits=3,avoided_days=list(range(7)))
    result = run(request(('DEMO 108',), preferences=prefs))
    assert len(result.schedules) == 1
    assert result.schedules[0].courses[0].sections[0].meetings[0].kind == 'asynchronous'
    result = run(request(('DEMO 110',)))
    assert all(s.courses[0].sections[0].number == 'A' for s in result.schedules)
    assert result.filtered_courses[0].rejected_reasons['unknown_meeting_time'] == 1


def test_internal_component_conflicts_and_crosslist_duplicates_are_detected():
    data = snapshot()
    for section in data.sections:
        if section.course_id == 'DEMO 103' and section.component == 'lab':
            lecture = next(s for s in data.sections if s.id == section.required_component_ids[0])
            section.meetings = lecture.meetings
    assert run(request(('DEMO 103',)), data).filtered_courses[0].rejected_reasons['internal_component_conflict'] == 2
    data = snapshot()
    for section in data.sections:
        if section.course_id in {'DEMO 101','DEMO 102'}: section.crosslist_group_id = 'same-physical-class'
    result = run(request(('DEMO 101','DEMO 102')), data)
    assert not result.schedules
    assert any(d.code == 'required_courses_conflict' for d in result.diagnostics)


def test_date_disjoint_classes_can_share_the_same_clock_time():
    data = snapshot()
    for section in data.sections:
        if section.course_id == 'DEMO 101': section.meetings = [meeting(start_date=date(2027,1,11),end_date=date(2027,1,17))]
        if section.course_id == 'DEMO 102': section.meetings = [meeting(start_date=date(2027,1,18),end_date=date(2027,1,24))]
    assert run(request(('DEMO 101','DEMO 102')), data).schedules


@pytest.mark.parametrize(('preferences','code'), [
    (dict(minimum_credits=0,target_credits=0,maximum_credits=0),'required_credits_exceed_maximum'),
    (dict(minimum_credits=10,target_credits=10,maximum_credits=10),'minimum_credits_unreachable'),
])
def test_credit_impossibility_has_proven_diagnostics(preferences, code):
    result = run(request(preferences=SchedulePreferences(**preferences)))
    assert not result.schedules and result.search_complete and result.nodes_visited == 0
    assert any(d.code == code for d in result.diagnostics)


def test_optional_unavailable_course_does_not_block_a_required_one():
    data = snapshot()
    for section in data.sections:
        if section.course_id == 'DEMO 102': section.meetings = [Meeting(kind='arranged')]
    req = request(('DEMO 101','DEMO 102'))
    req.selections[1].required = False
    result = run(req,data)
    assert result.schedules and all(len(s.courses)==1 for s in result.schedules)


def test_preferred_time_changes_ranking_without_breaking_constraints():
    morning = run(request(preferences=SchedulePreferences(minimum_credits=3,target_credits=3,maximum_credits=3,preferred_time='morning')))
    afternoon = run(request(preferences=SchedulePreferences(minimum_credits=3,target_credits=3,maximum_credits=3,preferred_time='afternoon')))
    assert morning.schedules[0].courses[0].sections[0].number == 'A'
    assert afternoon.schedules[0].courses[0].sections[0].number == 'B'


def test_compact_days_preference_can_trade_a_short_gap_for_fewer_meeting_days():
    data = snapshot()
    for section in data.sections:
        if section.course_id=='DEMO 101': section.meetings=[meeting(day=0 if section.number=='A' else 1)]
        if section.course_id=='DEMO 102': section.meetings=[meeting(600,650,day=0 if section.number=='A' else 2)]
    req=request(('DEMO 101','DEMO 102'),preferences=SchedulePreferences(minimum_credits=6,target_credits=6,maximum_credits=6))
    spread=run(req,data).schedules[0]
    req.preferences.compact_days=True
    compact=run(req,data).schedules[0]
    spread_days={m.weekday for c in spread.courses for s in c.sections for m in s.meetings}
    compact_days={m.weekday for c in compact.courses for s in c.sections for m in s.meetings}
    assert len(spread_days)==2 and len(compact_days)==1


def test_search_budget_reports_partial_results_not_false_impossibility():
    result = run(request(node_budget=1))
    assert not result.search_complete and not result.schedules
    assert {d.code for d in result.diagnostics} == {'search_limit'}
    partial = run(request(node_budget=2))
    assert not partial.search_complete and len(partial.schedules)==1


def test_suggestion_section_restrictions_and_provenance_are_revalidated():
    data = snapshot()
    audit = reviewed(['Research and Discovery'])
    recommended = recommend(audit,data,'sample-spring-2027',load_rule_packs())
    req = request(('DEMO 102',))
    req.reviewed = audit
    req.selections[0].source = 'suggestion'
    req.selections[0].requirement_ids = ['req-0']
    req.rule_revisions = recommended.resolution.rule_revisions
    req.expected_snapshot_digest = recommended.snapshot_digest
    result = run(req,data)
    assert all(s.courses[0].sections[0].number=='B' for s in result.schedules)
    assert result.schedules[0].courses[0].possible_requirement_ids == ['req-0']
    req.expected_snapshot_digest = '0'*64
    with pytest.raises(InvalidReview, match='Course data changed'): run(req,data)
    req.expected_snapshot_digest = recommended.snapshot_digest
    req.rule_revisions = {}
    with pytest.raises(InvalidReview, match='Curriculum definitions changed'): run(req,data)


def test_multiple_possible_matches_do_not_imply_joint_fulfillment():
    data = snapshot()
    data.designations = [d for d in data.designations if not(d.course_id=='DEMO 102' and d.attribute_id=='FC-CREATE')]
    data.designations.append(CourseDesignation(course_id='DEMO 102',edition='2026-2027',attribute_id='FC-CREATE',
        term_id='sample-spring-2027',section_id='demo-102-a',source_snapshot_id=data.sources[0].id))
    audit = reviewed(['Creative Expression, Practice, and Production','Research and Discovery'])
    recommended = recommend(audit,data,'sample-spring-2027',load_rule_packs())
    req = request(('DEMO 102',)); req.reviewed = audit
    req.selections[0] = SchedulingSelection(course_id='DEMO 102',required=True,source='suggestion',requirement_ids=['req-0','req-1'])
    req.rule_revisions = recommended.resolution.rule_revisions; req.expected_snapshot_digest = recommended.snapshot_digest
    result = run(req,data)
    assert len(result.schedules)==2
    assert all(len(s.courses[0].possible_requirement_ids)==1 for s in result.schedules)


def test_variable_credit_values_are_explicit_and_decimal_totals_are_exact():
    assert run(request(('DEMO 109',),preferences=SchedulePreferences(minimum_credits=2,target_credits=2,maximum_credits=2))).schedules[0].total_credits == 2
    assert not run(request(('DEMO 109',),preferences=SchedulePreferences(minimum_credits=3,target_credits=3,maximum_credits=3))).schedules
    data = snapshot()
    for c in data.courses:
        if c.id=='DEMO 101' and c.edition=='2026-2027': c.credits_min=c.credits_max=1.5
    for s in data.sections:
        if s.course_id=='DEMO 101': s.credit_value=1.5
    for b in data.bundles:
        if b.course_id=='DEMO 101': b.credits=1.5
    data = CatalogSnapshot.model_validate(data.model_dump(mode='json'))
    assert run(request(('DEMO 101','DEMO 104'),preferences=SchedulePreferences(minimum_credits=2.5,target_credits=2.5,maximum_credits=2.5)),data).schedules[0].total_credits == 2.5


@pytest.mark.parametrize('fields', [dict(minimum_credits=5,target_credits=3),dict(earliest_start=1000,latest_end=900),dict(avoided_days=[1,1])])
def test_invalid_preferences_are_rejected(fields):
    with pytest.raises(ValidationError): SchedulePreferences(**fields)


def test_api_rejects_stale_duplicate_and_empty_requests_and_returns_bounded_results(client):
    body = request(result_limit=1).model_dump(mode='json')
    result = client.post('/api/v1/schedules/generate',json=body)
    assert result.status_code == 200 and len(result.json()['schedules'])==1
    assert result.json()['search_complete'] and result.json()['classification']=='fictional'
    body['selections'] *= 2
    assert client.post('/api/v1/schedules/generate',json=body).status_code == 422
    body['selections'] = []
    assert client.post('/api/v1/schedules/generate',json=body).status_code == 422
    body = request().model_dump(mode='json'); body['reviewed']['audit']['requirements'][0]['label']='Changed'
    assert client.post('/api/v1/schedules/generate',json=body).json()['error']['code']=='stale_review'
