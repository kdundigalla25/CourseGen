import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.catalog import find_snapshot, search_courses
from app.catalog_models import CatalogSnapshot
from app.curriculum import DATA_ROOT
from app.ingestion import publish_snapshot, validate_file


@pytest.fixture
def data():
    return json.loads((DATA_ROOT / 'samples' / 'fictional-demo-v1.json').read_text(encoding='utf-8'))


def test_fictional_fixture_is_valid_and_exercises_offering_cases(data):
    snapshot = CatalogSnapshot.model_validate(data)
    assert len({c.id for c in snapshot.courses}) == 10
    assert len(snapshot.sections) == 22 and len(snapshot.bundles) == 20
    assert any(m.kind == 'unknown' for s in snapshot.sections for m in s.meetings)
    assert any(m.kind == 'asynchronous' for s in snapshot.sections for m in s.meetings)
    assert any(m.start_minute and m.start_minute >= 1080 for s in snapshot.sections for m in s.meetings)
    assert any(c.credits_min != c.credits_max for c in snapshot.courses)


def test_historical_and_section_specific_attributes_keep_their_scope(data):
    snapshot = CatalogSnapshot.model_validate(data)
    old = search_courses(snapshot, query='DEMO 101', attribute_id='FC-AESTH')
    new = search_courses(snapshot, query='DEMO 101', term_id='sample-spring-2027', attribute_id='FC-AESTH')
    assert old.total == 1 and old.courses[0].course.edition == '2024-2025'
    assert new.total == 0
    research = search_courses(snapshot, query='DEMO 102', term_id='sample-spring-2027', attribute_id='RESEARCH')
    assert research.courses[0].designations[-1].section_id == 'demo-102-b'


@pytest.mark.parametrize('mutation', [
    'duplicate_section', 'unknown_source', 'missing_course_edition', 'bad_term', 'bad_time', 'partial_dates',
    'outside_term', 'async_timed', 'empty_meetings', 'bad_link', 'missing_component', 'unknown_linkage',
    'wrong_credit_total', 'separate_lab_credit', 'duplicate_bundle', 'repeated_bundle_section', 'bad_designation',
    'mixed_classification', 'public_no_provenance', 'infinite_credits',
])
def test_invalid_imports_are_rejected(data, mutation):
    if mutation == 'duplicate_section': data['sections'].append(deepcopy(data['sections'][0]))
    elif mutation == 'unknown_source': data['courses'][0]['source_snapshot_id'] = 'missing'
    elif mutation == 'missing_course_edition': data['courses'][0]['edition'] = 'unversioned'
    elif mutation == 'bad_term': data['sections'][0]['term_id'] = 'missing'
    elif mutation == 'bad_time': data['sections'][0]['meetings'][0]['end_minute'] = 500
    elif mutation == 'partial_dates': data['sections'][0]['meetings'][0]['start_date'] = '2027-01-11'
    elif mutation == 'outside_term': data['sections'][0]['meetings'][0].update(start_date='2026-01-01', end_date='2026-02-01')
    elif mutation == 'async_timed': data['sections'][0]['modality'] = 'asynchronous'
    elif mutation == 'empty_meetings': data['sections'][0]['meetings'] = []
    elif mutation == 'bad_link': data['sections'][0]['required_component_ids'] = ['missing']
    elif mutation == 'missing_component': next(b for b in data['bundles'] if b['course_id'] == 'DEMO 103')['section_ids'].pop()
    elif mutation == 'unknown_linkage': data['sections'][0]['linkage_status'] = 'unknown'
    elif mutation == 'wrong_credit_total': data['bundles'][0]['credits'] = 6
    elif mutation == 'separate_lab_credit': next(b for b in data['bundles'] if b['course_id'] == 'DEMO 104')['credits'] = 0
    elif mutation == 'duplicate_bundle':
        duplicate = deepcopy(data['bundles'][0]); duplicate['id'] = 'duplicate-combination'; data['bundles'].append(duplicate)
    elif mutation == 'repeated_bundle_section': data['bundles'][0]['section_ids'] *= 2
    elif mutation == 'bad_designation': data['designations'][-1]['section_id'] = 'missing'
    elif mutation == 'mixed_classification': data['sources'][0]['classification'] = 'public'
    elif mutation == 'public_no_provenance':
        data['classification'] = 'public'; data['sources'][0]['classification'] = 'public'
    else: data['courses'][0]['credits_max'] = float('inf')
    with pytest.raises(ValidationError): CatalogSnapshot.model_validate(data)


def test_component_credits_are_counted_once_and_independent_lab_retains_credit(data):
    snapshot = CatalogSnapshot.model_validate(data)
    bundled = next(b for b in snapshot.bundles if b.course_id == 'DEMO 103')
    standalone = next(b for b in snapshot.bundles if b.course_id == 'DEMO 104')
    assert len(bundled.section_ids) == 2 and bundled.credits == 4
    assert standalone.credits == 1


def test_public_snapshot_requires_timezone_aware_provenance(data):
    data['classification'] = data['sources'][0]['classification'] = 'public'
    data['sources'][0].update(source_url='https://catalog.unc.edu/', retrieved_at='2026-11-07T00:00:00Z')
    assert CatalogSnapshot.model_validate(data).classification == 'public'
    data['sources'][0]['retrieved_at'] = '2026-11-07T00:00:00'
    with pytest.raises(ValidationError): CatalogSnapshot.model_validate(data)


def test_publication_is_validated_atomic_and_immutable(data, tmp_path):
    snapshot = CatalogSnapshot.model_validate(data)
    target = publish_snapshot(snapshot, tmp_path)
    before = target.read_bytes()
    assert validate_file(target) == snapshot
    assert publish_snapshot(snapshot, tmp_path) == target
    changed = snapshot.model_copy(deep=True)
    changed.description = 'Changed data'
    with pytest.raises(ValueError): publish_snapshot(changed, tmp_path)
    changed.sections[0].required_component_ids = ['missing']
    with pytest.raises(ValidationError): publish_snapshot(changed, tmp_path)
    assert target.read_bytes() == before
    assert list(tmp_path.glob('*.tmp')) == []


def test_catalog_api_is_explicit_about_samples_and_snapshot_selection(client):
    terms = client.get('/api/v1/terms')
    assert terms.status_code == 200
    assert terms.json()[0]['classification'] == 'fictional'
    assert 'Not official UNC' in terms.json()[0]['notice']
    params = dict(snapshot_id='fictional-demo-v1', term_id='sample-spring-2027')
    courses = client.get('/api/v1/courses', params={**params, 'limit': 3}).json()
    assert courses['total'] == 10 and len(courses['courses']) == 3
    options = client.get('/api/v1/courses/DEMO%20103/sections', params=params)
    assert options.status_code == 200 and len(options.json()['bundles']) == 2
    assert client.get('/api/v1/courses', params={'snapshot_id': '../../missing'}).status_code == 404
    assert client.get('/api/v1/courses').status_code == 422
    assert client.get('/api/v1/courses', params={**params, 'limit': 101}).status_code == 422


def test_corrupt_catalog_is_reported_without_partial_success(client, monkeypatch):
    def invalid(): raise ValueError('Bad public snapshot')
    monkeypatch.setattr('app.main.available_terms', invalid)
    response = client.get('/api/v1/terms')
    assert response.status_code == 503 and response.json()['error']['code'] == 'invalid_catalog_data'
