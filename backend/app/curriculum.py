import re
from pathlib import Path

from app.models import AuditDraft, ReviewedAudit
from app.audit_review import validate_reviewed
from app.rule_models import (
    AvailableCurricula, CurriculumResolution, GenEdRulePack, ProgramRulePack,
    ProgramSelection, SelectionEvidence,
)

DATA_ROOT = Path(__file__).resolve().parents[2] / 'data'


def resolve_reviewed(reviewed: ReviewedAudit, packs: AvailableCurricula) -> CurriculumResolution:
    validate_reviewed(reviewed)
    resolution = resolve_curriculum(reviewed.audit, packs)
    if any(issue.code in {'conflicting_entry_terms', 'conflicting_catalog_years'} for issue in reviewed.unresolved_issues):
        resolution.state = 'conflict'
        if resolution.gen_ed_version:
            resolution.rule_revisions.pop(resolution.gen_ed_version, None)
        resolution.gen_ed_version = None
        resolution.method = 'unresolved'
        resolution.warnings.append('Conflicting starting-term or catalog evidence was left unresolved during review.')
    return resolution


def normalized(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()


def load_rule_packs(root: Path = DATA_ROOT) -> AvailableCurricula:
    gen_ed = [GenEdRulePack.model_validate_json(path.read_text(encoding='utf-8')) for path in sorted((root / 'curricula').glob('*.json'))]
    programs = [ProgramRulePack.model_validate_json(path.read_text(encoding='utf-8')) for path in sorted((root / 'programs').glob('*.json'))]
    packs = [*gen_ed, *programs]
    if len({pack.id for pack in packs}) != len(packs):
        raise ValueError('Rule pack IDs must be unique')
    if len({pack.cohort_year for pack in gen_ed}) != len(gen_ed):
        raise ValueError('Only one active pack per cohort is supported')
    program_keys = [(normalized(name), pack.requirement_term) for pack in programs for name in pack.audit_program_names]
    if len(set(program_keys)) != len(program_keys):
        raise ValueError('Program aliases/terms must resolve unambiguously')
    return AvailableCurricula(gen_ed=gen_ed, programs=programs)


def resolve_curriculum(audit: AuditDraft, packs: AvailableCurricula) -> CurriculumResolution:
    curriculum = audit.curriculum
    loaded = {pack.cohort_year: pack for pack in packs.gen_ed}
    labels = {normalized(item.label) for item in audit.requirements}
    evidence: list[SelectionEvidence] = []
    warnings = ['Rule packs cover category definitions and selected candidate mappings, not complete degree evaluation or exemption policies.']
    signature_years: set[int] = set()
    signature_scopes: set[frozenset[int]] = set()
    for pack in packs.gen_ed:
        rules = {rule.id: rule for rule in pack.requirements}
        if all(any(normalized(alias) in labels for alias in rules[key].audit_labels) for key in pack.signature_rule_ids):
            signature_years.update(pack.signature_cohort_years)
            signature_scopes.add(frozenset(pack.signature_cohort_years))
            evidence.append(SelectionEvidence(kind='requirement_signature', value=pack.id))

    programs = []
    for name, term in sorted(curriculum.program_terms.items()):
        matches = [pack for pack in packs.programs if term == pack.requirement_term and normalized(name) in {normalized(alias) for alias in pack.audit_program_names}]
        programs.append(ProgramSelection(name=name, requirement_term=term,
            pack_id=matches[0].id if len(matches) == 1 else None, state='selected' if len(matches) == 1 else 'unsupported'))
        evidence.append(SelectionEvidence(kind='program_term', value=f'{name}: {term}'))

    years: set[int] = set()
    entry_needs_review = False
    conflict = bool(signature_scopes) and not set.intersection(*(set(scope) for scope in signature_scopes))
    if curriculum.entry_term:
        evidence.append(SelectionEvidence(kind='entry_term', value=curriculum.entry_term))
        match = re.fullmatch(r'(\d{4}) (Fall|Spr|Spring)', curriculum.entry_term)
        if match:
            calendar_year = int(match[1])
            years = {calendar_year if match[2] == 'Fall' else calendar_year - 1}
            conflict = conflict or (curriculum.starting_year is not None and curriculum.starting_year != calendar_year)
        else:
            entry_needs_review = True
            warnings.append('Summer or unrecognized starting terms need manual cohort confirmation; no Fall cohort was assumed.')
    elif curriculum.starting_year:
        # Without a semester, a calendar year can straddle two entering cohorts.
        years = {curriculum.starting_year - 1, curriculum.starting_year}
        evidence.append(SelectionEvidence(kind='starting_year', value=str(curriculum.starting_year)))
    if curriculum.reported_catalog_year:
        evidence.append(SelectionEvidence(kind='catalog_label', value=curriculum.reported_catalog_year))
        catalog_year = int(curriculum.reported_catalog_year[:4])
        if years:
            if catalog_year not in years:
                conflict = True
            else:
                years &= {catalog_year}
        # Catalog labels alone never stand in for starting-year evidence.

    if signature_years and years and not years & signature_years and years <= loaded.keys():
        conflict = True
    if years and not conflict:
        # A known profile cannot rule out a cohort whose rules are not loaded.
        candidates = (years & signature_years) | (years - loaded.keys()) if signature_years else years
    else:
        candidates = years | signature_years

    selected = None
    method = 'unresolved'
    if not conflict and len(candidates) == 1:
        year = next(iter(candidates))
        if year in loaded and not entry_needs_review and (years or signature_years == {year}):
            selected = loaded[year].id
            method = 'metadata' if years else 'requirements'
    if conflict:
        state = 'conflict'
        warnings.append('Starting-term, catalog or positive requirement evidence disagrees. Confirm applicability before automatic matching.')
    elif selected:
        state = 'selected'
    elif candidates:
        state = 'ambiguous' if len(candidates) > 1 or entry_needs_review else 'unsupported'
        warnings.append('The available evidence does not identify one supported cohort. No newest-year fallback was applied.')
    else:
        state = 'unsupported'
        warnings.append('No supported entering cohort could be identified from this audit.')
    if any(year not in loaded for year in candidates):
        warnings.append('Some possible cohorts do not yet have verified rule packs.')
    revisions = {pack.id: pack.revision for pack in [*packs.gen_ed, *packs.programs]
                 if pack.id == selected or any(item.pack_id == pack.id for item in programs)}
    return CurriculumResolution(state=state, gen_ed_version=selected, method=method,
        candidate_versions=sorted(loaded[year].id for year in candidates if year in loaded),
        unsupported_cohort_years=sorted(candidates - loaded.keys()), evidence=evidence, programs=programs,
        warnings=warnings, rule_revisions=revisions)
