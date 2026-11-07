import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { components } from './api/schema';
import { SchedulePanel } from './SchedulePanel';

type Reviewed = components['schemas']['ReviewedAudit'];
type Term = components['schemas']['AvailableTerm'];
type Suggestions = components['schemas']['RecommendationResult'];
type Suggestion = components['schemas']['CourseSuggestion'];
type Course = components['schemas']['Course'];
type Search = components['schemas']['CourseSearchResult'];
type SectionOptions = components['schemas']['SectionOptions'];

export type SelectedCourse = {
  course_id: string; edition: string; title: string; required: boolean;
  source: 'suggestion' | 'manual'; matches: components['schemas']['RequirementMatch'][];
};

async function read<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || 'The course data could not be loaded.');
  return data as T;
}

const availabilityText: Record<Suggestion['availability'], string> = {
  available: 'Sections available — conflicts and eligibility still need checking',
  not_offered: 'No sections in the selected dataset',
  missing_catalog: 'Course details are not included in this dataset',
  unknown_meetings: 'Meeting times need verification before scheduling',
  no_qualifying_sections: 'No section combination meets this particular requirement in the dataset',
};

export function CoursePlanner({ reviewed }: { reviewed: Reviewed }) {
  const [terms, setTerms] = useState<Term[]>([]);
  const [termKey, setTermKey] = useState('');
  const [termsLoading, setTermsLoading] = useState(true);
  const [termError, setTermError] = useState('');
  const [termRetry, setTermRetry] = useState(0);
  const [result, setResult] = useState<Suggestions | null>(null);
  const [suggestionError, setSuggestionError] = useState('');
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [catalog, setCatalog] = useState<Search | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState('');
  const [selected, setSelected] = useState<SelectedCourse[]>([]);
  const [adding, setAdding] = useState<string | null>(null);
  const [selectionError, setSelectionError] = useState('');
  const context = useRef('');
  context.current = `${reviewed.revision}:${termKey}`;
  const term = terms.find(item => JSON.stringify([item.snapshot_id, item.term.id]) === termKey);

  useEffect(() => {
    const controller = new AbortController();
    setTermsLoading(true); setTermError('');
    fetch('/api/v1/terms', { signal: controller.signal }).then(read<Term[]>).then(data => {
      if (!controller.signal.aborted) setTerms(data);
    }).catch(error => { if (!controller.signal.aborted) setTermError(error instanceof Error ? error.message : 'Could not load semesters.'); })
      .finally(() => { if (!controller.signal.aborted) setTermsLoading(false); });
    return () => controller.abort();
  }, [termRetry]);

  useEffect(() => {
    if (!term) return;
    const controller = new AbortController();
    setLoading(true); setSuggestionError(''); setResult(null);
    fetch('/api/v1/recommendations', {
      method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reviewed, snapshot_id: term.snapshot_id, term_id: term.term.id }),
    }).then(read<Suggestions>).then(data => {
      if (!controller.signal.aborted) setResult(data);
    }).catch(error => { if (!controller.signal.aborted) setSuggestionError(error instanceof Error ? error.message : 'Could not load suggestions.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [term, reviewed, retry]);

  useEffect(() => {
    if (!term) return;
    const controller = new AbortController();
    setCatalogLoading(true); setCatalogError(''); setCatalog(null);
    const params = new URLSearchParams({ snapshot_id: term.snapshot_id, term_id: term.term.id, q: query, offset: String(offset), limit: '20' });
    fetch(`/api/v1/courses?${params}`, { signal: controller.signal }).then(read<Search>).then(data => {
      if (!controller.signal.aborted) setCatalog(data);
    }).catch(error => { if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : 'Could not search courses.'); })
      .finally(() => { if (!controller.signal.aborted) setCatalogLoading(false); });
    return () => controller.abort();
  }, [term, query, offset, retry]);

  function changeTerm(value: string) {
    context.current = `${reviewed.revision}:${value}`;
    setTermKey(value); setSelected([]); setResult(null); setCatalog(null);
    setSearch(''); setQuery(''); setOffset(0); setAdding(null); setSelectionError('');
    setLoading(false); setCatalogLoading(false); setSuggestionError(''); setCatalogError('');
  }
  function choose(suggestion: Suggestion) {
    if (!suggestion.selectable || selected.some(item => item.course_id === suggestion.course_id)) return;
    setSelected(value => [...value, { course_id: suggestion.course_id, edition: suggestion.edition, title: suggestion.title || suggestion.course_id,
      required: false, source: 'suggestion', matches: suggestion.matches }]);
  }
  async function addManual(course: Course) {
    if (!term || adding) return;
    const activeContext = context.current;
    setAdding(course.id); setSelectionError('');
    try {
      const params = new URLSearchParams({ snapshot_id: term.snapshot_id, term_id: term.term.id });
      const options = await fetch(`/api/v1/courses/${encodeURIComponent(course.id)}/sections?${params}`).then(read<SectionOptions>);
      if (context.current !== activeContext) return;
      const known = options.bundles.some(bundle => bundle.section_ids.every(id => {
        const section = options.sections.find(item => item.id === id);
        return section && section.meetings.every(meeting => !['unknown', 'arranged'].includes(meeting.kind));
      }));
      if (!known) throw new Error('This course has no verified section combination with known or asynchronous meetings. Check another course or dataset.');
      setSelected(value => value.some(item => item.course_id === course.id) ? value : [...value,
        { course_id: course.id, edition: course.edition, title: course.title, required: false, source: 'manual', matches: [] }]);
    } catch (error) { if (context.current === activeContext) setSelectionError(error instanceof Error ? error.message : 'Could not check this course.'); }
    finally { if (context.current === activeContext) setAdding(null); }
  }
  function submitSearch(event: FormEvent) { event.preventDefault(); setQuery(search.trim()); setOffset(0); }

  function suggestionCard(course: Suggestion) {
    const chosen = selected.some(item => item.course_id === course.course_id);
    return <article key={course.course_id} className="suggestion-card" aria-label={`Suggestion ${course.course_id}`}>
      <div className="record-heading"><strong>{course.course_id}</strong><span>{course.title}</span></div>
      <p className="caption">{availabilityText[course.availability]}{course.credits_min != null && ` · ${course.credits_min === course.credits_max ? course.credits_min : `${course.credits_min}–${course.credits_max}`} credits`}</p>
      <p><strong>Could help with:</strong> {course.matches.map(match => match.label).join('; ')}</p>
      {course.matches.map(match => <details key={match.requirement_id}><summary>Why it could help: {match.label}</summary><p>{match.explanation}</p>{match.section_options.length > 0 ? <p>Qualifying section options: {match.section_options.join(', ')}. These are alternatives.</p> : <p>No qualifying section with known or asynchronous meetings is available for this particular requirement in the selected dataset.</p>}{match.notes.map((note, index) => <p className="caption" key={index}>{note}</p>)}<p>{match.sources.map(source => <a key={source.id} href={source.url} target="_blank" rel="noreferrer">Published rule ({source.edition}) </a>)}</p></details>)}
      {course.matches.length > 1 && <p className="notice">These are possible matches. We have not established that the course can count toward all of them together.</p>}
      <p className="eligibility">{course.eligibility === 'conditional' ? 'Eligibility depends on work still in progress. Verify before enrolling.' : 'Eligibility has not been verified. Check prerequisites and enrollment restrictions.'}</p>
      {course.prerequisite_text && <p className="caption">Catalog prerequisite text: {course.prerequisite_text}</p>}
      <details><summary>Things to verify before choosing sections</summary>{course.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</details>
      <button type="button" className="secondary" disabled={!course.selectable || chosen} onClick={() => choose(course)}>{chosen ? `Added ${course.course_id}` : `Add ${course.course_id}`}</button>
    </article>;
  }

  const available = result?.suggestions.filter(course => course.selectable) ?? [];
  const other = result?.suggestions.filter(course => !course.selectable) ?? [];
  return <section className="course-planner" aria-labelledby="course-planner-title">
    <div className="section-label">STEP 03 <span>From reviewed progress to possible courses</span></div>
    <h2 id="course-planner-title">Choose courses to explore.</h2>
    <p>Suggestions start with requirements you marked not satisfied. Add courses you want to consider, or search the selected dataset yourself.</p>
    <label className="semester-picker">Semester and course data<select value={termKey} onChange={event => changeTerm(event.target.value)} disabled={termsLoading}><option value="">Choose semester data</option>{terms.map(item => <option key={JSON.stringify([item.snapshot_id, item.term.id])} value={JSON.stringify([item.snapshot_id, item.term.id])}>{item.term.name} — {item.classification === 'fictional' ? 'Fictional sample data' : `Imported data${item.sources[0]?.retrieved_at ? ` · ${item.sources[0].retrieved_at}` : ''}`}</option>)}</select></label>
    {termsLoading && <p role="status">Loading semester data…</p>}
    {termError && <div role="alert" className="error">{termError} <button type="button" onClick={() => setTermRetry(value => value + 1)}>Retry semesters</button></div>}
    {!termsLoading && !termError && terms.length === 0 && <p className="notice">No semester data is available. Import a validated dataset before choosing courses.</p>}
    {term && <><p className="notice"><strong>{term.notice}</strong></p><details className="data-sources"><summary>Where this course data comes from</summary>{term.sources.map(source => <p key={source.id}>{source.classification === 'fictional' ? 'Invented development fixture; no official refresh or availability is implied.' : <>{source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">Source</a>} · Retrieved {source.retrieved_at || 'time unavailable'}</>}</p>)}</details></>}
    {loading && <p role="status">Finding possible matches for your reviewed requirements…</p>}
    {suggestionError && <div role="alert" className="error">{suggestionError} <button type="button" onClick={() => setRetry(value => value + 1)}>Retry suggestions</button></div>}
    {result && <>
      {result.resolution.state !== 'selected' && <p className="notice">Your Gen Ed curriculum needs clarification before automatic Gen Ed suggestions are available. Check your starting-year details above. Verified program suggestions may still be shown.</p>}
      <h3>Possible courses for your remaining requirements</h3><p className="caption">{result.counting_notice}</p>
      {available.length === 0 && <p>No new selectable course matches were found in this dataset. Review the items below or use course search; this does not mean your requirements are complete.</p>}
      {available.map(suggestionCard)}
      {other.length > 0 && <details className="unavailable-options"><summary>Other mapped courses without selectable sections ({other.length})</summary>{other.map(suggestionCard)}</details>}
      {result.manual_requirements.length > 0 && <details className="manual-items"><summary>Requirements that need your input ({result.manual_requirements.length})</summary>{result.manual_requirements.map(item => <article key={item.requirement_id}><strong>{item.label}</strong><p>{item.message}</p></article>)}</details>}
      {result.excluded_courses.length > 0 && <details><summary>Courses not suggested again</summary>{result.excluded_courses.map((item, index) => <p key={index}>{item.course_id}: {item.message}</p>)}</details>}
    </>}
    {term && <section className="course-search" aria-label="Course search"><h3>Search courses yourself</h3><p className="caption">Adding a course from search does not establish which requirements it fulfills. Verify eligibility and section details.</p><form onSubmit={submitSearch}><label>Course code or title<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search this dataset" /></label><button type="submit" className="secondary">Search courses</button></form>
      {catalogLoading && <p role="status">Searching courses…</p>}{catalogError && <p role="alert" className="error">{catalogError}</p>}
      {catalog && <><p className="caption">{catalog.total} matching course{catalog.total === 1 ? '' : 's'} in this term.</p>{catalog.courses.map(({ course }) => <article className="search-result" key={`${course.id}:${course.edition}`}><div><strong>{course.id}</strong> · {course.title}{reviewed.audit.attempts?.some(attempt => attempt.course_id === course.id && attempt.status !== 'unknown') && <p className="notice">Your history already lists this course as completed or in progress. Verify repeat eligibility before adding it again manually.</p>}</div><button type="button" className="secondary" disabled={!!adding || selected.some(item => item.course_id === course.id)} onClick={() => addManual(course)}>{adding === course.id ? 'Checking sections…' : selected.some(item => item.course_id === course.id) ? `Added ${course.id}` : `Add from search ${course.id}`}</button></article>)}<div className="actions"><button type="button" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Previous courses</button><button type="button" disabled={offset + catalog.limit >= catalog.total} onClick={() => setOffset(value => value + 20)}>More courses</button></div></>}
      {selectionError && <p role="alert" className="error">{selectionError}</p>}
    </section>}
    <section className="selected-courses" aria-label="Courses to consider"><h3>Courses to consider ({selected.length})</h3><p className="caption">Each course starts as optional. Mark it required only if you want every generated schedule to include it. Suggestions are alternatives, not a recommended combined course load.</p>
      {selected.length === 0 && <p>Add courses above to start your list.</p>}
      {selected.map(course => <article key={course.course_id}><strong>{course.course_id}</strong> · {course.title}<p className="caption">{course.source === 'manual' ? 'Added from search; requirement coverage is unverified.' : 'Added from suggestions; confirm the qualifying sections when scheduling.'}</p><label className="checkbox-label"><input type="checkbox" checked={course.required} onChange={event => setSelected(value => value.map(item => item.course_id === course.course_id ? { ...item, required: event.target.checked } : item))} />Must include {course.course_id}</label><button type="button" className="text-button danger" onClick={() => setSelected(value => value.filter(item => item.course_id !== course.course_id))}>Remove {course.course_id}</button></article>)}
      <p className="caption">Set your preferences below when your course list is ready. Editing reviewed progress or changing semester data clears the list.</p>
    </section>
    {term && <SchedulePanel reviewed={reviewed} term={term} selected={selected} ruleRevisions={result?.resolution.rule_revisions} snapshotDigest={result?.snapshot_digest} suggestionsLoading={loading} />}
  </section>;
}
