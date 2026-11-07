"""Optional aggregate-only validation against the privately supplied reference PDFs.

Run with --freshman PATH --junior PATH. No PDFs, text, or student names are saved.
Expected counts were reconciled with the supplied samples; these are not generic
expectations for all students in either cohort.
"""
import argparse
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import app


def verify(client, path: Path, *, year: int, program: str, program_term: str,
           attempts: int, in_progress: int, requirements: int, pages: int):
    data = path.read_bytes()
    result = client.post('/api/v1/audits/parse', files={'file': ('tracker.pdf', data, 'application/pdf')})
    assert result.status_code == 200, 'Parsing failed'
    draft = result.json()
    assert draft['page_count'] == pages
    assert draft['curriculum']['starting_year'] == year
    assert draft['curriculum']['program_terms'][program] == program_term
    assert draft['curriculum']['gen_ed_version'] is None
    assert len(draft['attempts']) == attempts
    assert sum(item['status'] == 'in_progress' for item in draft['attempts']) == in_progress
    assert len(draft['requirements']) == requirements
    # The observed later-page name is independent from first-page header formatting.
    header = (PdfReader(io.BytesIO(data)).pages[1].extract_text() or '').splitlines()[1].strip()
    assert header not in result.text, 'Page identity header leaked'
    body = {'original': draft, 'edited': draft, 'confirmed': True,
            'acknowledged_issue_ids': [item['id'] for item in draft['issues'] if item['review_required']]}
    reviewed = client.post('/api/v1/audits/review', json=body)
    assert reviewed.status_code == 200, 'Review failed'
    assert reviewed.json()['review_state'] == 'confirmed'
    assert reviewed.json()['changes'] == []
    resolution = client.post('/api/v1/curricula/resolve', json=reviewed.json())
    assert resolution.status_code == 200
    assert resolution.json()['gen_ed_version'] == f'ideas-{year}-{year+1}'
    selected_program = next(item for item in resolution.json()['programs'] if item['name'] == program)
    assert selected_program['state'] == 'selected'
    recommendations = client.post('/api/v1/recommendations', json={
        'reviewed': reviewed.json(), 'snapshot_id': 'fictional-demo-v1', 'term_id': 'sample-spring-2027'})
    assert recommendations.status_code == 200
    planned = recommendations.json()
    assert planned['audit_revision'] == reviewed.json()['revision']
    assert planned['classification'] == 'fictional'
    assert all(item['course_id'].startswith('DEMO ') for item in planned['suggestions'] if item['selectable'])
    assert all(item['eligibility'] != 'eligible' for item in planned['suggestions'])
    if year == 2026:
        assert any(item['selectable'] for item in planned['suggestions'])
    assert any(item['reason'] == 'non_course' for item in planned['manual_requirements'])
    available = [item for item in planned['suggestions'] if item['selectable']][:2]
    choices = [dict(course_id=item['course_id'], required=True, source='suggestion',
                    requirement_ids=[match['requirement_id'] for match in item['matches']]) for item in available]
    # A sample with no unmet automatically mapped coursework exercises the explicit
    # manual-search path; the app does not fabricate a requirement or recommendation.
    if not choices:
        choices = [dict(course_id='DEMO 101', required=True, source='manual', requirement_ids=[])]
    schedules = client.post('/api/v1/schedules/generate', json=dict(reviewed=reviewed.json(),
        snapshot_id='fictional-demo-v1', term_id='sample-spring-2027', selections=choices,
        rule_revisions=planned['resolution']['rule_revisions'], expected_snapshot_digest=planned['snapshot_digest'],
        preferences=dict(minimum_credits=3,target_credits=6 if len(choices)>1 else 3,maximum_credits=18)))
    assert schedules.status_code == 200
    assert schedules.json()['schedules'] and schedules.json()['search_complete']
    assert all(len(schedule['courses'])==len(choices) for schedule in schedules.json()['schedules'])
    query = json.loads(schedules.request.content)
    chosen = schedules.json()['schedules'][0]
    export = dict(schedule_request=query, schedule_id=chosen['id'])
    record = client.post('/api/v1/schedules/export/json', json=export)
    assert record.status_code == 200 and record.json()['schedule'] == chosen
    assert 'reviewed' not in record.json() and 'audit_revision' not in record.json()
    calendar = client.post('/api/v1/schedules/export/ics', json=export)
    assert calendar.status_code == 200 and 'BEGIN:VEVENT' in calendar.text
    path_label = 'suggested' if available else 'explicit manual sample'
    print(f'PASS: {year} reference; {pages} pages, {attempts} course records, {in_progress} in progress, {requirements} requirement items; review, rule resolution, sample suggestions, {path_label} scheduling and JSON/ICS exports verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freshman', type=Path, required=True)
    parser.add_argument('--junior', type=Path, required=True)
    args = parser.parse_args()
    with TestClient(app) as client:
        verify(client, args.freshman, year=2026, program='Business Administration Major', program_term='2026 Fall', attempts=27, in_progress=6, requirements=73, pages=3)
        verify(client, args.junior, year=2024, program='Computer Science (BS) Major', program_term='2025 Fall', attempts=54, in_progress=5, requirements=66, pages=4)
