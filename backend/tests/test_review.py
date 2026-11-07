import copy

import pytest

from app.models import ReviewRequest
from app.audit_review import review
from test_parser import fixture_draft


def request_data():
    draft, _ = fixture_draft('cohort_2024')
    original = draft.model_dump(mode='json')
    return {'original': original, 'edited': copy.deepcopy(original), 'confirmed': True,
            'acknowledged_issue_ids': [issue.id for issue in draft.issues if issue.review_required]}


def test_confirmation_records_edits_and_changes_revision_without_server_storage(client):
    body = request_data()
    original = copy.deepcopy(body['original'])
    first = client.post('/api/v1/audits/review', json=body)
    assert first.status_code == 200
    assert first.json()['review_state'] == 'confirmed'
    assert first.json()['changes'] == []
    body['edited']['attempts'][0]['status'] = 'completed'
    second = client.post('/api/v1/audits/review', json=body)
    assert second.status_code == 200
    result = second.json()
    assert result['revision'] != first.json()['revision']
    assert any(change['field'].startswith('attempts.') for change in result['changes'])
    mixed = next(r for r in result['audit']['requirements'] if r['label'] == 'Additional COMP Courses')
    assert mixed['completion'] == 'completed'
    assert body['original'] == original
    assert client.post('/api/v1/audits/review', json=body).json()['revision'] == result['revision']


@pytest.mark.parametrize('field', ['confirmed', 'acknowledged_issue_ids'])
def test_confirmation_requires_explicit_review_and_flag_acknowledgment(client, field):
    body = request_data()
    body[field] = False if field == 'confirmed' else []
    response = client.post('/api/v1/audits/review', json=body)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_review'


def test_add_remove_and_corrections_are_validated(client):
    body = request_data()
    deleted = body['edited']['attempts'].pop()
    for requirement in body['edited']['requirements']:
        requirement['attempt_ids'] = [key for key in requirement['attempt_ids'] if key != deleted['id']]
    body['edited']['attempts'].append({'id': 'manual-1', 'course_id': 'TEST 101', 'title': 'Added record', 'term': '2025 Fall', 'credits': 3, 'status': 'unknown'})
    body['edited']['requirements'].append({'id': 'manual-req', 'label': 'Manual elective', 'attempt_ids': ['manual-1'], 'reported_status': 'unknown'})
    result = client.post('/api/v1/audits/review', json=body)
    assert result.status_code == 200
    assert any(c['field'] == 'attempts.manual-1' and c['before'] is None for c in result.json()['changes'])
    assert any(c['field'] == f"attempts.{deleted['id']}" and c['after'] is None for c in result.json()['changes'])
    assert any(issue['target_id'] == 'manual-1' and issue['code'] == 'unknown_attempt_status' for issue in result.json()['unresolved_issues'])
    assert any(issue['target_id'] == 'manual-req' for issue in result.json()['unresolved_issues'])


@pytest.mark.parametrize('mutation', ['cycle', 'missing_parent', 'missing_attempt', 'duplicate_id', 'bad_catalog', 'bad_term', 'inconsistent_entry', 'bad_course', 'negative_credits', 'empty_label'])
def test_invalid_review_has_safe_field_errors(client, mutation):
    body = request_data()
    audit = body['edited']
    if mutation == 'cycle':
        audit['requirements'][0]['parent_id'] = audit['requirements'][0]['id']
    elif mutation == 'missing_parent':
        audit['requirements'][0]['parent_id'] = 'missing'
    elif mutation == 'missing_attempt':
        audit['requirements'][0]['attempt_ids'] = ['missing']
    elif mutation == 'duplicate_id':
        audit['attempts'].append(audit['attempts'][0])
    elif mutation == 'bad_catalog':
        audit['curriculum']['reported_catalog_year'] = '2024-2026'
    elif mutation == 'bad_term':
        audit['curriculum']['program_terms']['New Major'] = 'unknown semester'
    elif mutation == 'inconsistent_entry':
        audit['curriculum']['starting_year'] = 2026
    elif mutation == 'bad_course':
        audit['attempts'][0]['course_id'] = 'not a code'
    elif mutation == 'negative_credits':
        audit['attempts'][0]['credits'] = -1
    else:
        audit['requirements'][0]['label'] = ''
    response = client.post('/api/v1/audits/review', json=body)
    assert response.status_code == 422
    assert response.json()['error']['code'] in {'invalid_request', 'invalid_review'}
    assert 'input' not in response.json()['error']


def test_review_cannot_turn_a_rule_id_or_curriculum_guess_into_verified_mapping():
    body = request_data()
    body['edited']['curriculum']['gen_ed_version'] = 'invented'
    body['edited']['requirements'][0]['rule_id'] = 'invented'
    result = review(ReviewRequest(**body))
    assert result.audit.curriculum.gen_ed_version is None
    assert result.audit.requirements[0].rule_id is None


def test_cleared_flags_remain_in_evidence_but_not_unresolved_list(client):
    body = request_data()
    unknown = next(r for r in body['edited']['requirements'] if r['reported_status'] == 'unknown')
    unknown['reported_status'] = 'not_satisfied'
    response = client.post('/api/v1/audits/review', json=body).json()
    assert any(i['code'] == 'unknown_requirement_status' for i in response['audit']['issues'])
    assert not any(i['code'] == 'unknown_requirement_status' for i in response['unresolved_issues'])
