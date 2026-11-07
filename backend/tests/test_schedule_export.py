from datetime import date
import json
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.schedule_export import ScheduleExportRequest, ExportError, calendar_bytes, fold, utc_time
from test_scheduling import request, run
from test_recommendations import snapshot


def export_request(req=None):
    req = req or request()
    result = run(req)
    req.expected_snapshot_digest = result.snapshot_digest
    req.rule_revisions = result.rule_revisions
    return ScheduleExportRequest(schedule_request=req, schedule_id=result.schedules[0].id)


def test_export_api_revalidates_and_omits_student_history(client):
    query = export_request()
    response = client.post('/api/v1/schedules/export/json', json=query.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data['schedule']['id'] == query.schedule_id
    assert data['snapshot_digest'] == query.schedule_request.expected_snapshot_digest
    assert data['classification'] == 'fictional'
    assert not {'reviewed', 'audit_revision', 'audit', 'attempts', 'pages'} & data.keys()
    assert 'Synthetic source' not in response.text
    assert response.headers['cache-control'] == 'no-store'
    response = client.post('/api/v1/schedules/export/ics', json=query.model_dump(mode='json'))
    assert response.status_code == 200
    assert 'BEGIN:VEVENT' in response.text and 'Not official UNC' in response.text.replace('\r\n ', '')
    query.schedule_id = 'not-in-results'
    assert client.post('/api/v1/schedules/export/json', json=query.model_dump(mode='json')).status_code == 404
    query = export_request()
    query.schedule_request.expected_snapshot_digest = '0' * 64
    assert client.post('/api/v1/schedules/export/json', json=query.model_dump(mode='json')).status_code == 422
    query = export_request()
    query.schedule_request.rule_revisions = None
    assert client.post('/api/v1/schedules/export/json', json=query.model_dump(mode='json')).status_code == 422


def test_calendar_actual_dates_dst_boundaries_and_stable_uids():
    query = export_request()
    result = run(query.schedule_request)
    chosen = result.schedules[0]
    chosen.courses[0].sections[0].meetings = [chosen.courses[0].sections[0].meetings[0]]
    m = chosen.courses[0].sections[0].meetings[0]
    m.weekday, m.start_minute, m.end_minute = 0, 540, 590
    m.start_date, m.end_date = date(2027,3,1), date(2027,3,15)
    term = snapshot().terms[0]
    body = calendar_bytes(chosen,result,term,query)
    assert body.count(b'BEGIN:VEVENT') == 3
    assert b'DTSTART:20270301T140000Z' in body
    assert b'DTSTART:20270315T130000Z' in body
    assert [line for line in body.splitlines() if not line.startswith(b'DTSTAMP:')] == [line for line in calendar_bytes(chosen,result,term,query).splitlines() if not line.startswith(b'DTSTAMP:')]
    m.start_date = m.end_date = date(2027,3,2)  # Tuesday has no Monday occurrence.
    with pytest.raises(ExportError, match='no dated fixed meetings'):
        calendar_bytes(chosen,result,term,query)


def test_missing_dates_fallback_and_source_dates_win():
    query = export_request()
    result, term = run(query.schedule_request), snapshot().terms[0]
    chosen = result.schedules[0]
    for section in chosen.courses[0].sections:
        for m in section.meetings: m.start_date = m.end_date = None
    term.start_date = term.end_date = None
    with pytest.raises(ExportError, match='dates are missing'):
        calendar_bytes(chosen,result,term,query)
    query.fallback_start, query.fallback_end = date(2027,1,11), date(2027,1,17)
    assert b'202701' in calendar_bytes(chosen,result,term,query)
    term.start_date, term.end_date = date(2027,3,15), date(2027,3,21)
    body = calendar_bytes(chosen,result,term,query)
    assert b'DTSTART:202703' in body and b'DTSTART:202701' not in body


def test_async_only_exports_json_but_does_not_invent_calendar_events(client):
    from app.scheduling_models import SchedulePreferences
    query = export_request(request(('DEMO 108',), preferences=SchedulePreferences(minimum_credits=3,target_credits=3,maximum_credits=3,avoided_days=list(range(7)))))
    assert client.post('/api/v1/schedules/export/json',json=query.model_dump(mode='json')).status_code == 200
    response = client.post('/api/v1/schedules/export/ics',json=query.model_dump(mode='json'))
    assert response.status_code == 422 and 'asynchronous' in response.text


def test_mixed_async_preserved_in_description_and_escaping():
    query = export_request(request(('DEMO 101','DEMO 108')))
    result, term = run(query.schedule_request), snapshot().terms[0]
    result.schedules[0].courses[1].sections[0].meetings[0].kind = 'asynchronous'
    course = result.schedules[0].courses[0]
    course.title = '長' * 100 + ',;\\\nBEGIN:VEVENT'
    body = calendar_bytes(result.schedules[0],result,term,query)
    assert all(len(line) <= 75 for line in body.split(b'\r\n'))
    unfolded = body.decode().replace('\r\n ', '')
    assert 'Asynchronous (no calendar events): DEMO 108' in unfolded
    assert r'\,\;\\\nBEGIN:VEVENT' in unfolded
    assert '\r\nBEGIN:VEVENT\r\n' in unfolded


def test_timezone_edge_cases_and_midnight():
    zone = ZoneInfo('America/New_York')
    assert utc_time(date(2027,1,11),1440,zone) == '20270112T050000Z'
    for day, minute in [(date(2027,3,14),150),(date(2027,11,7),90)]:
        with pytest.raises(ExportError,match='daylight-saving'):
            utc_time(day,minute,zone)
    assert all(len(line.encode()) <= 75 for line in fold('é'*100).split('\r\n'))


@pytest.mark.parametrize('fields', [dict(fallback_start='2027-01-01'),dict(fallback_start='2027-02-01',fallback_end='2027-01-01'),dict(fallback_start='2027-01-01',fallback_end='2029-01-01')])
def test_bad_fallback_dates_rejected(fields):
    with pytest.raises(ValidationError):
        ScheduleExportRequest(schedule_request=request(),schedule_id='example',**fields)
