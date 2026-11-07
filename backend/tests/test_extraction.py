import asyncio

import pytest
from pydantic import ValidationError

from app.audit_worker import extract
from app.models import Course, Meeting
from conftest import make_pdf


def upload(client, payload):
    return client.post('/api/v1/audits/parse', files={'file': ('private-name.pdf', payload, 'application/pdf')})


def test_tracker_extracts_all_pages_and_returns_reviewable_draft(client, tracker, caplog):
    response = upload(client, tracker)
    assert response.status_code == 200
    result = response.json()
    assert result['support'] == 'tracker_structure_detected'
    assert result['page_count'] == 2
    assert 'Ways of Knowing' in result['pages'][1]['text']
    assert result['curriculum']['reported_catalog_year'] == '2026-2027'
    assert result['curriculum']['starting_year'] == 2026
    assert result['curriculum']['gen_ed_version'] is None
    assert result['attempts'] == []
    assert len(result['requirements']) == 3
    assert result['review_state'] == 'needs_review'
    assert 'Synthetic Student' not in response.text
    assert '123456789' not in response.text
    assert 'Synthetic Student' not in caplog.text
    assert 'private-name.pdf' not in caplog.text


def test_page_local_identity_headers_are_removed_even_when_split_differently(client):
    payload = make_pdf([
        ['First Last 123456789', 'Program Requirement', 'Catalog Year 2024-2025', 'Satisfied: Foundations'],
        ['First Last', '123456789', '____________________', 'UNIVERSITY OF NORTH CAROLINA - CHAPEL HILL', 'Not Satisfied: Ways of Knowing'],
    ])
    response = upload(client, payload)
    assert response.status_code == 200
    assert 'First Last' not in response.text
    assert '123456789' not in response.text
    assert 'Ways of Knowing' in response.text


@pytest.mark.parametrize(('payload', 'code'), [
    (b'not a pdf', 'invalid_pdf'),
    (b'%PDF-corrupt', 'unreadable_pdf'),
    (make_pdf([['text']], 'password'), 'encrypted_pdf'),
    (make_pdf([[]]), 'no_text'),
    (make_pdf([[]] * 26), 'too_many_pages'),
    (make_pdf([]), 'empty_pdf'),
])
def test_bad_documents_have_safe_errors(client, payload, code):
    response = upload(client, payload)
    assert response.status_code == 422
    assert response.json()['error']['code'] == code
    assert 'Traceback' not in response.text


def test_unrelated_pdf_is_explicitly_unsupported(client):
    result = upload(client, make_pdf([['A different document']])).json()
    assert result['support'] == 'unsupported'
    assert any(issue['code'] == 'unsupported_layout' for issue in result['issues'])


def test_blank_page_is_flagged(client):
    result = upload(client, make_pdf([['Document text'], []])).json()
    assert any(issue['code'] == 'page_without_text' and issue['page'] == 2 for issue in result['issues'])


def test_oversized_body_is_rejected_before_parsing(client, monkeypatch):
    monkeypatch.setattr('app.main.MAX_REQUEST_BYTES', 1024)
    response = upload(client, b'%PDF-' + b'x' * 2048)
    assert response.status_code == 413
    assert response.json()['error']['code'] == 'file_too_large'


def test_file_limit_is_separate_from_multipart_overhead(client, monkeypatch):
    monkeypatch.setattr('app.main.MAX_UPLOAD_BYTES', 100)
    response = upload(client, b'%PDF-' + b'x' * 200)
    assert response.status_code == 413


def test_missing_file_is_safe(client):
    response = client.post('/api/v1/audits/parse')
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_request'


def test_worker_timeout_kills_process(client, tracker, monkeypatch):
    class SlowProcess:
        returncode = None
        killed = False

        async def communicate(self, data):
            await asyncio.sleep(1)

        def kill(self):
            self.killed = True
            self.returncode = -1

        async def wait(self):
            return self.returncode

    process = SlowProcess()

    async def create(*args, **kwargs):
        return process

    monkeypatch.setattr('app.main.asyncio.create_subprocess_exec', create)
    monkeypatch.setattr('app.main.EXTRACTION_TIMEOUT', 0.01)
    response = upload(client, tracker)
    assert response.json()['error']['code'] == 'extraction_timeout'
    assert process.killed


def test_extraction_character_limit(monkeypatch):
    monkeypatch.setattr('app.audit_worker.MAX_CHARACTERS', 5)
    assert extract(make_pdf([['Longer text']])) == {'error': 'too_much_text'}


def test_meeting_and_credit_invariants():
    with pytest.raises(ValidationError):
        Meeting(kind='timed', weekday=0, start_minute=600, end_minute=500)
    with pytest.raises(ValidationError):
        Meeting(kind='unknown', start_minute=600)
    with pytest.raises(ValidationError):
        Course(id='TEST 100', title='Test', credits_min=4, credits_max=3, source_snapshot_id='fictional')
    assert Meeting(kind='asynchronous').start_minute is None
