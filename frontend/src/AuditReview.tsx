import { useEffect, useState } from 'react';
import type { components } from './api/schema';

type Draft = components['schemas']['AuditDraft'];
type Attempt = components['schemas']['CourseAttempt'];
type Requirement = components['schemas']['AuditRequirement'];
type Curriculum = components['schemas']['CurriculumSelection'];
type Issue = components['schemas']['Issue'];
type Evidence = components['schemas']['Evidence'];
type Reviewed = components['schemas']['ReviewedAudit'];
type Editable = Draft & { curriculum: Curriculum; attempts: Attempt[]; requirements: Requirement[]; issues: Issue[] };

function editable(draft: Draft): Editable {
  return structuredClone({ ...draft, curriculum: draft.curriculum ?? { method: 'unresolved' }, attempts: draft.attempts ?? [], requirements: draft.requirements ?? [], issues: draft.issues ?? [] });
}

function SourceEvidence({ evidence }: { evidence?: Evidence[] }) {
  if (!evidence?.length) return <p className="caption">Manually added record.</p>;
  return <details className="evidence"><summary>Compare with your Tracker text</summary><ul>{evidence.map((line, index) => <li key={index}><span>Page {line.page}, line {line.line}</span> {line.text}</li>)}</ul></details>;
}

function numeric(value: string) { return value === '' ? null : Number(value); }

function questionText(issue: Issue): string {
  switch (issue.code) {
    case 'unknown_attempt_status': return "We couldn't tell whether this course is completed or in progress. Choose its status in Course history.";
    case 'non_catalog_credit': return "Your Tracker lists general credit without a course number. Keep it if it matches your Tracker; you don't need to invent a course code.";
    case 'duplicate_attempt': return 'This credit appears more than once. Check whether these are separate awards before removing either record.';
    case 'conflicting_attempt_records': return 'This course appears with different grades or credit markers. Check whether the entries are separate attempts.';
    case 'incomplete_course_row': return 'Part of this course entry is missing. Check its term and credits against your Tracker.';
    case 'unknown_requirement_status': return "The PDF doesn't clearly say whether this requirement is satisfied. Check your Tracker, or leave it Unknown if you're unsure.";
    case 'missing_entry_term': return "We couldn't find when you started at UNC. Add your starting term if you know it.";
    case 'conflicting_entry_terms': return 'We found different starting terms. Check when you first enrolled at UNC.';
    case 'conflicting_catalog_years': return 'We found different catalog-year labels. Check the label in your Tracker.';
    case 'conflicting_program_terms': return "Check the requirement term for your major or minor. It can differ from your starting year.";
    case 'entry_catalog_disagreement': return 'Your starting year and catalog label differ. Check both against your Tracker.';
    case 'unparsed_requirement_text': return "There may be a condition we couldn't read clearly. Compare the supporting text with your Tracker.";
    case 'parser_item_limit': return 'Some entries could not be included because this document is too large to review in full. Compare with your complete Tracker.';
    default: return issue.message;
  }
}

function stillNeedsChecking(issue: Issue, audit: Editable): boolean {
  const course = audit.attempts.find(row => row.id === issue.target_id);
  const requirement = audit.requirements.find(row => row.id === issue.target_id);
  if (issue.target_id && !course && !requirement) return false;
  if (issue.code === 'unknown_attempt_status' && course?.status !== 'unknown') return false;
  if (issue.code === 'non_catalog_credit' && course?.course_id) return false;
  if (issue.code === 'incomplete_course_row' && course?.term && course.credits != null) return false;
  if (issue.code === 'unknown_requirement_status' && requirement?.reported_status !== 'unknown') return false;
  if (['missing_entry_term', 'conflicting_entry_terms'].includes(issue.code) && audit.curriculum.entry_term) return false;
  if (issue.code === 'conflicting_catalog_years' && audit.curriculum.reported_catalog_year) return false;
  if (issue.code === 'entry_catalog_disagreement' && audit.curriculum.starting_year && audit.curriculum.reported_catalog_year?.startsWith(String(audit.curriculum.starting_year))) return false;
  return true;
}

export function AuditReview({ original, onReviewChange }: { original: Draft; onReviewChange?: (reviewed: Reviewed | null) => void }) {
  const [audit, setAudit] = useState<Editable>(() => editable(original));
  const [tab, setTab] = useState<'metadata' | 'courses' | 'requirements'>('metadata');
  const [courseFilter, setCourseFilter] = useState('all');
  const [requirementFilter, setRequirementFilter] = useState('open');
  const [acknowledged, setAcknowledged] = useState(false);
  const [reviewed, setReviewed] = useState<Reviewed | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [programName, setProgramName] = useState('');
  const [programTerm, setProgramTerm] = useState('');
  const [focusTarget, setFocusTarget] = useState<string | null>(null);
  const requiredIssues = audit.issues.filter(issue => issue.review_required);
  const questions = (reviewed ? reviewed.unresolved_issues : requiredIssues).filter(issue => stillNeedsChecking(issue, audit));
  const questionGroups = new Map<string, Issue[]>();
  for (const issue of questions) {
    const key = issue.target_id ?? 'metadata';
    questionGroups.set(key, [...(questionGroups.get(key) ?? []), issue]);
  }

  useEffect(() => {
    if (!focusTarget) return;
    const element = document.getElementById(`review-${focusTarget}`);
    element?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
    element?.focus({ preventScroll: true });
    setFocusTarget(null);
  }, [focusTarget, tab]);

  function checkItem(id: string) {
    const isCourse = audit.attempts.some(row => row.id === id);
    setTab(id === 'metadata' ? 'metadata' : isCourse ? 'courses' : 'requirements');
    setCourseFilter('all'); setRequirementFilter('all'); setFocusTarget(id);
  }

  function edit(change: (value: Editable) => Editable) {
    setAudit(change); setReviewed(null); setAcknowledged(false); setError('');
    onReviewChange?.(null);
  }
  function curriculum(change: Partial<Curriculum>) { edit(value => ({ ...value, curriculum: { ...value.curriculum, ...change } })); }
  function attempt(id: string, change: Partial<Attempt>) { edit(value => ({ ...value, attempts: value.attempts.map(row => row.id === id ? { ...row, ...change } : row) })); }
  function requirement(id: string, change: Partial<Requirement>) { edit(value => ({ ...value, requirements: value.requirements.map(row => row.id === id ? { ...row, ...change } : row) })); }
  function removeAttempt(id: string) {
    edit(value => ({ ...value, attempts: value.attempts.filter(row => row.id !== id), requirements: value.requirements.map(row => ({ ...row, attempt_ids: row.attempt_ids?.filter(key => key !== id) })) }));
  }
  function removeRequirement(row: Requirement) {
    edit(value => ({ ...value, requirements: value.requirements.filter(item => item.id !== row.id).map(item => item.parent_id === row.id ? { ...item, parent_id: row.parent_id } : item) }));
  }
  function addAttempt() {
    setCourseFilter('all');
    edit(value => ({ ...value, attempts: [...value.attempts, { id: `manual-${crypto.randomUUID()}`, course_id: null, raw_course_code: '', title: '', term: null, credits: null, grade: null, status: 'unknown', origin: 'unknown', evidence: [], needs_review: true }] }));
  }
  function addRequirement() {
    setRequirementFilter('all');
    edit(value => ({ ...value, requirements: [...value.requirements, { id: `manual-${crypto.randomUUID()}`, label: '', parent_id: null, kind: 'unknown', reported_status: 'unknown', completion: 'unknown', attempt_ids: [], amounts: [], evidence: [], needs_review: true }] }));
  }
  function addProgram() {
    const name = programName.trim();
    if (!name || !programTerm.trim()) return;
    if (name in (audit.curriculum.program_terms ?? {})) { setError('That program already exists. Edit its requirement term below.'); return; }
    curriculum({ program_terms: { ...audit.curriculum.program_terms, [name]: programTerm.trim() } });
    setProgramName(''); setProgramTerm('');
  }

  async function confirm() {
    if (!acknowledged || saving) return;
    setSaving(true); setError('');
    try {
      const response = await fetch('/api/v1/audits/review', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ original, edited: audit, confirmed: true, acknowledged_issue_ids: requiredIssues.map(issue => issue.id) }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error?.message || 'The review could not be confirmed.');
      const confirmed = result as Reviewed;
      setReviewed(confirmed); setAudit(editable(confirmed.audit));
      onReviewChange?.(confirmed);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not reach the review service.'); }
    finally { setSaving(false); }
  }

  const courses = audit.attempts.filter(row => courseFilter === 'all' || (courseFilter === 'flagged' ? row.needs_review || row.status === 'unknown' : row.status === courseFilter));
  const requirements = audit.requirements.filter(row => requirementFilter === 'all' || (requirementFilter === 'flagged' ? row.needs_review || row.reported_status === 'unknown' : row.reported_status !== 'satisfied'));
  const terms = audit.curriculum.program_terms ?? {};

  return <section className="review-panel" aria-labelledby="review-title">
    <div className="section-label">STEP 02 <span>Review before planning</span></div>
    <h2 id="review-title">Make sure your progress looks right.</h2>
    <p className="review-intro">We read your course history and degree requirements from your PDF. Compare them with your Tracker, correct anything that looks wrong, and add anything missing. A requirement marked satisfied may still depend on a course you're taking now.</p>
    <div className="review-stats"><span><strong>{audit.attempts.filter(row => row.status === 'completed').length}</strong> completed course / credit entries</span><span><strong>{audit.attempts.filter(row => row.status === 'in_progress').length}</strong> courses in progress</span></div>
    <section className="check-questions" aria-labelledby="questions-title"><h3 id="questions-title">{questions.length ? 'A few things to double-check' : 'No unanswered questions from this import'}</h3><p className="caption">A question means part of the PDF was unclear. It does not mean you failed a requirement. You can leave a detail Unknown if you're unsure.</p>{[...questionGroups].map(([id, issues]) => {
      const name = audit.attempts.find(row => row.id === id)?.raw_course_code || audit.requirements.find(row => row.id === id)?.label || 'Starting year & programs';
      return <article className="check-question" key={id}><strong>{name}</strong>{issues.map(issue => <p key={issue.id}>{questionText(issue)}</p>)}<button className="text-button" type="button" onClick={() => checkItem(id)}>Check {name}</button></article>;
    })}{!questions.length && <p className="caption">Please still check your course history and requirements before using them for planning.</p>}</section>
    <div className="review-tabs" role="group" aria-label="Review sections">{(['metadata', 'courses', 'requirements'] as const).map(value => <button key={value} type="button" aria-pressed={tab === value} onClick={() => setTab(value)}>{value === 'metadata' ? 'Starting year & programs' : value === 'courses' ? 'Course history' : 'Requirements'}</button>)}</div>
    <fieldset className="review-fields" disabled={saving}>
      {tab === 'metadata' && <div id="review-metadata" tabIndex={-1}>
        <h3>Starting year & programs</h3><p className="caption">Check when you started at UNC and the program terms shown on your Tracker. Your major or minor can use a different requirement year from your Gen Ed curriculum.</p>
        <div className="field-grid">
          <label>Starting year<input type="number" min="1900" max="2100" value={audit.curriculum.starting_year ?? ''} onChange={event => curriculum({ starting_year: numeric(event.target.value) })} /></label>
          <label>Starting term<input placeholder="2024 Fall" value={audit.curriculum.entry_term ?? ''} onChange={event => curriculum({ entry_term: event.target.value || null })} /></label>
          <label>Reported catalog year<input placeholder="2024-2025" value={audit.curriculum.reported_catalog_year ?? ''} onChange={event => curriculum({ reported_catalog_year: event.target.value || null })} /></label>
        </div>
        <div className="program-list">{Object.entries(terms).map(([name, term]) => <div className="program-row" key={name}><label>{name}<input aria-label={`Requirement term for ${name}`} value={term} onChange={event => curriculum({ program_terms: { ...terms, [name]: event.target.value } })} /></label><button type="button" className="text-button danger" aria-label={`Remove program ${name}`} onClick={() => curriculum({ program_terms: Object.fromEntries(Object.entries(terms).filter(([key]) => key !== name)) })}>Remove</button></div>)}</div>
        <div className="field-grid add-program"><label>New program name<input value={programName} onChange={event => setProgramName(event.target.value)} placeholder="Major, minor or degree program" /></label><label>New program requirement term<input value={programTerm} onChange={event => setProgramTerm(event.target.value)} placeholder="2025 Fall" /></label><button type="button" className="secondary" onClick={addProgram} disabled={!programName.trim() || !programTerm.trim()}>Add program</button></div>
        <SourceEvidence evidence={audit.curriculum.evidence} />
      </div>}
      {tab === 'courses' && <div>
        <div className="review-toolbar"><h3>Course history</h3><label>Show course records<select value={courseFilter} onChange={event => setCourseFilter(event.target.value)}><option value="all">All records</option><option value="in_progress">In progress</option><option value="completed">Completed / awarded credit</option><option value="flagged">Needs review</option></select></label><button type="button" className="secondary" onClick={addAttempt}>+ Add course record</button></div>
        <p className="caption">Transfer, exam and placement records retain their original markers. General credit without a course number remains non-selectable. Repeated awards may be distinct; verify before removing them.</p>
        {!courses.length && <p>No course records match this filter. Add missing records or change the filter.</p>}
        {courses.map(row => <article className="record-card" key={row.id} id={`review-${row.id}`} tabIndex={-1} aria-label={`Course record ${row.raw_course_code || row.course_id || 'new'}`}>
          <div className="record-heading"><strong>{row.course_id || row.raw_course_code || 'New course record'}</strong>{(questionGroups.has(row.id) || row.status === 'unknown' || !row.course_id || !row.term || row.credits == null) && <span className="flag">Needs review</span>}<button type="button" className="text-button danger" aria-label={`Remove course ${row.id}`} onClick={() => removeAttempt(row.id)}>Remove</button></div>
          <div className="field-grid course-grid"><label>Course code<input value={row.raw_course_code || row.course_id || ''} placeholder="COMP 210" onChange={event => { const code = event.target.value.toUpperCase().replace(/\s+/g, ' '); attempt(row.id, { raw_course_code: code, course_id: code.includes('----') || !code.trim() ? null : code.trim() }); }} /></label>
            <label>Course title<input value={row.title ?? ''} onChange={event => attempt(row.id, { title: event.target.value })} /></label>
            <label>Term<input value={row.term ?? ''} placeholder="2025 Spr" onChange={event => attempt(row.id, { term: event.target.value || null })} /></label>
            <label>Credits<input type="number" min="0" step="0.25" value={row.credits ?? ''} onChange={event => attempt(row.id, { credits: numeric(event.target.value) })} /></label>
            <label>Grade / credit marker<input value={row.grade ?? ''} onChange={event => attempt(row.id, { grade: event.target.value.toUpperCase() || null })} /></label>
            <label>Course status<select value={row.status ?? 'unknown'} onChange={event => attempt(row.id, { status: event.target.value as Attempt['status'] })}><option value="completed">Completed / awarded credit</option><option value="in_progress">In progress</option><option value="unknown">Unknown / needs review</option></select></label>
            <label>Credit origin<select value={row.origin ?? 'unknown'} onChange={event => attempt(row.id, { origin: event.target.value as Attempt['origin'] })}><option value="institution">UNC coursework</option><option value="transfer">Transfer</option><option value="exam">Exam / placement</option><option value="unknown">Unknown</option></select></label>
          </div><SourceEvidence evidence={row.evidence} />
        </article>)}
      </div>}
      {tab === 'requirements' && <div>
        <div className="review-toolbar"><h3>Degree requirements</h3><label>Show requirements<select value={requirementFilter} onChange={event => setRequirementFilter(event.target.value)}><option value="open">Not satisfied & unknown</option><option value="all">All requirements</option><option value="flagged">Needs review</option></select></label><button type="button" className="secondary" onClick={addRequirement}>+ Add requirement</button></div>
        <p className="caption">Counts and statuses reflect the PDF. Events, elective pools and policies stay separate from course selections. A potential course-to-requirement mapping has not been verified.</p>
        {!requirements.length && <p>No requirements match this filter. You can show all requirements or add a missing one.</p>}
        {requirements.map(row => <article className="record-card" key={row.id} id={`review-${row.id}`} tabIndex={-1} aria-label={`Requirement ${row.label || 'new'}`}>
          <div className="record-heading"><strong>{row.label || 'New requirement'}</strong>{(questionGroups.has(row.id) || row.reported_status === 'unknown') && <span className="flag">Needs review</span>}<button type="button" className="text-button danger" aria-label={`Remove requirement ${row.id}`} onClick={() => removeRequirement(row)}>Remove</button></div>
          <div className="field-grid"><label className="wide-field">Requirement description<input value={row.label} onChange={event => requirement(row.id, { label: event.target.value })} /></label>
            <label>Reported status<select value={row.reported_status ?? 'unknown'} onChange={event => requirement(row.id, { reported_status: event.target.value as Requirement['reported_status'] })}><option value="not_satisfied">Not satisfied</option><option value="satisfied">Satisfied in Tracker</option><option value="unknown">Unknown / needs review</option></select></label>
            <label>Requirement type<select value={row.kind ?? 'unknown'} onChange={event => requirement(row.id, { kind: event.target.value as Requirement['kind'] })}>{['group', 'course', 'elective', 'policy', 'non_course', 'unknown'].map(kind => <option value={kind} key={kind}>{kind.replace('_', ' ')}</option>)}</select></label>
            <label>Parent group<select value={row.parent_id ?? ''} onChange={event => requirement(row.id, { parent_id: event.target.value || null })}><option value="">Top level</option>{audit.requirements.filter(item => item.id !== row.id).map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          </div>
          <p className="caption">{reviewed ? 'Reviewed evidence' : 'Parsed evidence'}: {(row.completion ?? 'unknown').replace('_', ' ')}. Completion evidence is recalculated on confirmation.</p>
          {(row.amounts ?? []).map((amount, index) => <div className="amount-row" key={index}><label>Count unit<select value={amount.unit} onChange={event => requirement(row.id, { amounts: row.amounts?.map((item, i) => i === index ? { ...item, unit: event.target.value as typeof amount.unit } : item) })}><option value="courses">Courses</option><option value="credits">Credits</option><option value="gpa">GPA</option></select></label>{(['required', 'taken', 'needed', 'in_progress'] as const).map(name => <label key={name}>{name === 'taken' && amount.unit === 'gpa' ? 'Actual' : name === 'in_progress' ? 'In progress' : name}<input type="number" min="0" step="any" value={amount[name] ?? ''} onChange={event => requirement(row.id, { amounts: row.amounts?.map((item, i) => i === index ? { ...item, [name]: numeric(event.target.value) } : item) })} /></label>)}<button type="button" className="text-button danger" onClick={() => requirement(row.id, { amounts: row.amounts?.filter((_, i) => i !== index) })}>Remove count</button></div>)}
          <button type="button" className="text-button" onClick={() => requirement(row.id, { amounts: [...(row.amounts ?? []), { unit: 'courses', required: null, taken: null, needed: null }] })}>+ Add count</button>
          <details className="attempt-links"><summary>Course evidence links ({row.attempt_ids?.length ?? 0})</summary><p className="caption">These links say where the PDF used a course. They do not establish a verified fulfillment rule.</p>{audit.attempts.map(course => <label className="checkbox-label" key={course.id}><input type="checkbox" checked={row.attempt_ids?.includes(course.id) ?? false} onChange={event => requirement(row.id, { attempt_ids: event.target.checked ? [...(row.attempt_ids ?? []), course.id] : row.attempt_ids?.filter(id => id !== course.id) })} />{course.raw_course_code || course.course_id || 'Unidentified course'} · {course.term || 'Unknown term'} · {course.title}</label>)}</details>
          <SourceEvidence evidence={row.evidence} />
        </article>)}
      </div>}
      <div className="confirm-box"><h3>Use these details for planning</h3><p className="caption">This tells the planner to use the details you've checked. It does not mark requirements complete in UNC's records. Anything left Unknown will stay marked as needing review.</p><label className="checkbox-label"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />I've checked my details against my Tracker and reviewed anything marked Needs review.</label><div className="actions"><button type="button" className="primary" disabled={!acknowledged || saving || !!reviewed} onClick={confirm}>{saving ? 'Checking details…' : reviewed ? 'Progress confirmed' : 'Use this progress'}</button><span className="caption">If you edit a detail, we'll ask you to confirm again.</span></div></div>
    </fieldset>
    {error && <p className="error" role="alert">{error}</p>}
    <div role="status" aria-live="polite">{reviewed && <div className="confirmed"><strong>Your review is complete.</strong>{questions.length > 0 && <p>Some details still need checking. They remain marked for review; confirming has not made them satisfied.</p>}<p>{onReviewChange ? 'Choose semester data below to explore course suggestions.' : 'Your checked details are ready for course planning.'} Your progress stays in this tab and clears when you refresh.</p></div>}</div>
  </section>;
}
