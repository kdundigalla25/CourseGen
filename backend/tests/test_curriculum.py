from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.audit_review import review
from app.curriculum import load_rule_packs, resolve_curriculum
from app.models import AuditRequirement, CurriculumSelection, ReviewRequest
from app.rule_models import AvailableCurricula, GenEdRulePack
from test_parser import fixture_draft


def resolve(name='cohort_2024', **metadata):
    audit, _ = fixture_draft(name)
    audit.curriculum = CurriculumSelection(**metadata)
    return resolve_curriculum(audit, load_rule_packs())


def test_rule_packs_are_sourced_independent_and_explicitly_partial():
    packs = load_rule_packs()
    assert {p.cohort_year for p in packs.gen_ed} == {2024, 2025, 2026}
    assert all(p.coverage == 'partial' and p.limitations and p.sources for p in [*packs.gen_ed, *packs.programs])
    old = next(p for p in packs.gen_ed if p.cohort_year == 2024)
    new = next(p for p in packs.gen_ed if p.cohort_year == 2026)
    assert 'fy-triple' in {r.id for r in old.requirements}
    assert 'fy-triple' not in {r.id for r in new.requirements}
    assert 'interdisciplinary' not in {r.id for r in old.requirements}
    assert 'interdisciplinary' in {r.id for r in new.requirements}
    assert all(policy.enforcement == 'not_evaluated' for policy in new.policies)


def test_starting_cohort_does_not_use_major_term():
    result = resolve(entry_term='2024 Fall', starting_year=2024, reported_catalog_year='2024-2025',
                     program_terms={'Computer Science (BS) Major': '2025 Fall'})
    assert result.state == 'selected' and result.gen_ed_version == 'ideas-2024-2025'
    assert result.programs[0].pack_id == 'cs-bs-2025-fall'
    assert result.method == 'metadata'
    assert set(result.rule_revisions) == {'ideas-2024-2025', 'cs-bs-2025-fall'}


def test_same_new_requirement_profile_cannot_distinguish_2025_from_2026():
    result = resolve('cohort_2026')
    assert result.state == 'ambiguous' and result.gen_ed_version is None
    assert result.candidate_versions == ['ideas-2025-2026', 'ideas-2026-2027']
    assert any(e.kind == 'requirement_signature' for e in result.evidence)


def test_single_loaded_old_signature_is_not_unique_when_older_cohorts_unloaded():
    result = resolve()
    assert result.state == 'ambiguous' and result.gen_ed_version is None
    assert result.candidate_versions == ['ideas-2024-2025']
    assert result.unsupported_cohort_years == [2022, 2023]


@pytest.mark.parametrize(('term', 'starting', 'edition'), [('2026 Fall', 2026, '2026-2027'), ('2025 Fall', 2025, '2025-2026'), ('2026 Spring', 2026, '2025-2026')])
def test_supported_starting_terms_select_the_correct_academic_cohort(term, starting, edition):
    result = resolve('cohort_2026', entry_term=term, starting_year=starting, reported_catalog_year=edition)
    assert result.state == 'selected' and result.gen_ed_version == f'ideas-{edition}'


def test_missing_or_incomplete_evidence_does_not_fall_back_to_latest():
    audit, _ = fixture_draft('cohort_2024')
    audit.requirements = []
    audit.curriculum = CurriculumSelection(reported_catalog_year='2026-2027', program_terms={'Unknown Major': '2026 Fall'})
    result = resolve_curriculum(audit, load_rule_packs())
    assert result.state == 'unsupported' and result.gen_ed_version is None
    audit.curriculum = CurriculumSelection(entry_term='2026 Fall', starting_year=2026)
    assert resolve_curriculum(audit, load_rule_packs()).gen_ed_version == 'ideas-2026-2027'


@pytest.mark.parametrize('metadata', [
    dict(entry_term='2026 Fall', starting_year=2026, reported_catalog_year='2024-2025'),
    dict(entry_term='2024 Fall', starting_year=2026),
    dict(entry_term='2026 Fall', starting_year=2026),
])
def test_positive_metadata_or_requirement_conflicts_need_review(metadata):
    result = resolve(**metadata)
    assert result.state == 'conflict' and result.gen_ed_version is None


def test_incompatible_positive_requirement_profiles_are_not_combined_into_a_guess():
    audit, _ = fixture_draft('cohort_2024')
    audit.requirements += [AuditRequirement(id='new-lab', label='First Year Data Lab'), AuditRequirement(id='new-interdisciplinary', label='Interdisciplinary Course')]
    assert resolve_curriculum(audit, load_rule_packs()).state == 'conflict'


def test_unsupported_year_and_program_do_not_inherit_a_newer_pack():
    result = resolve(entry_term='2023 Fall', starting_year=2023, program_terms={'Computer Science (BS) Major': '2024 Fall'})
    assert result.state == 'unsupported' and result.unsupported_cohort_years == [2023]
    assert result.programs[0].state == 'unsupported' and result.programs[0].pack_id is None


def test_unloaded_future_year_is_not_disproved_by_a_known_requirement_profile():
    result = resolve('cohort_2026', entry_term='2027 Fall', starting_year=2027)
    assert result.state == 'unsupported' and result.gen_ed_version is None
    assert result.unsupported_cohort_years == [2027]
    partial = resolve('cohort_2026', starting_year=2027)
    assert partial.state == 'ambiguous' and partial.gen_ed_version is None


def test_summer_entry_needs_review_even_when_a_signature_matches_one_loaded_year():
    audit, _ = fixture_draft('cohort_2026')
    audit.curriculum = CurriculumSelection(entry_term='2026 Summer', starting_year=2026)
    pack = load_rule_packs().gen_ed[-1].model_copy(deep=True)
    pack.signature_cohort_years = [2026]
    result = resolve_curriculum(audit, AvailableCurricula(gen_ed=[pack], programs=[]))
    assert result.gen_ed_version is None and result.state == 'ambiguous'


def test_new_verified_unique_signature_requires_data_only_and_does_not_invent_starting_year():
    audit, _ = fixture_draft('cohort_2024')
    audit.curriculum = CurriculumSelection()
    original = load_rule_packs().gen_ed[0].model_dump(mode='json')
    original.update(id='ideas-2030-2031', cohort_year=2030, catalog_year='2030-2031', signature_cohort_years=[2030])
    pack = GenEdRulePack.model_validate(original)
    result = resolve_curriculum(audit, AvailableCurricula(gen_ed=[pack], programs=[]))
    assert result.gen_ed_version == 'ideas-2030-2031' and result.method == 'requirements'
    assert audit.curriculum.starting_year is None


def test_rule_references_and_cycles_are_validated():
    pack = load_rule_packs().gen_ed[0].model_dump(mode='json')
    bad = deepcopy(pack)
    bad['requirements'][0]['source_ids'] = ['missing']
    with pytest.raises(ValidationError): GenEdRulePack.model_validate(bad)
    bad = deepcopy(pack)
    bad['requirements'][0]['child_ids'] = [bad['requirements'][0]['id']]
    with pytest.raises(ValidationError): GenEdRulePack.model_validate(bad)


def test_resolution_api_requires_a_confirmed_unchanged_revision(client):
    draft, _ = fixture_draft('cohort_2024')
    confirmed = review(ReviewRequest(original=draft, edited=draft, confirmed=True,
        acknowledged_issue_ids=[i.id for i in draft.issues if i.review_required])).model_dump(mode='json')
    result = client.post('/api/v1/curricula/resolve', json=confirmed)
    assert result.status_code == 200 and result.json()['gen_ed_version'] == 'ideas-2024-2025'
    confirmed['audit']['curriculum']['starting_year'] = 2023
    assert client.post('/api/v1/curricula/resolve', json=confirmed).status_code == 422
    assert client.get('/api/v1/curricula').status_code == 200
