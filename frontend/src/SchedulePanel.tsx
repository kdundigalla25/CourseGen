import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { components } from './api/schema';
import { ScheduleComparison } from './ScheduleComparison';
import { ScheduleDetails } from './ScheduleDetails';
import type { SelectedCourse } from './CoursePlanner';

type Reviewed = components['schemas']['ReviewedAudit'];
type Term = components['schemas']['AvailableTerm'];
type Result = components['schemas']['ScheduleResult'];
type Preferences = components['schemas']['SchedulePreferences'];
const days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const minutes = (value: string) => { const [hour, minute] = value.split(':').map(Number); return hour * 60 + minute; };

export function SchedulePanel({ reviewed, term, selected, ruleRevisions, snapshotDigest, suggestionsLoading = false }: {
  reviewed: Reviewed; term: Term; selected: SelectedCourse[];
  ruleRevisions?: Record<string,string>; snapshotDigest?: string;
  suggestionsLoading?: boolean;
}) {
  const [minimum, setMinimum] = useState('3');
  const [maximum, setMaximum] = useState('18');
  const [target, setTarget] = useState('12');
  const [earliest, setEarliest] = useState('08:00');
  const [latest, setLatest] = useState('21:00');
  const [avoided, setAvoided] = useState<number[]>([]);
  const [preferred, setPreferred] = useState<'none'|'morning'|'afternoon'>('none');
  const [compact, setCompact] = useState(false);
  const [limit, setLimit] = useState('10');
  const [completed, setCompleted] = useState<{ key: string; result: Result; request: components['schemas']['ScheduleRequest'] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const suggestionsUnavailable = selected.some(course => course.source === 'suggestion') && (!ruleRevisions || !snapshotDigest);
  const generationDisabled = busy || suggestionsLoading || suggestionsUnavailable || selected.length===0 || selected.length>12;
  const key = JSON.stringify({ revision: reviewed.revision, term: [term.snapshot_id,term.term.id], selected,
    minimum,maximum,target,earliest,latest,avoided,preferred,compact,limit,ruleRevisions,snapshotDigest,suggestionsLoading });
  const current = useRef(key); current.current = key;
  const result = completed?.key === key ? completed.result : null;

  useEffect(() => {
    controller.current?.abort(); setBusy(false); setError(''); setCompleted(null);
    return () => controller.current?.abort();
  }, [key]);

  async function generate(event: FormEvent) {
    event.preventDefault();
    if (generationDisabled) return;
    const preferences: Preferences = {
      minimum_credits: Number(minimum), maximum_credits: Number(maximum), target_credits: Number(target),
      earliest_start: minutes(earliest), latest_end: minutes(latest), avoided_days: avoided,
      preferred_time: preferred, compact_days: compact,
    };
    if (!(Number(minimum) <= Number(target) && Number(target) <= Number(maximum))) {
      setError('Put your minimum, target and maximum credits in order.'); return;
    }
    if (minutes(earliest) >= minutes(latest)) { setError('Earliest start must be before latest end.'); return; }
    controller.current?.abort();
    const requestController = new AbortController(); controller.current = requestController;
    const requestKey = key;
    setBusy(true); setError(''); setCompleted(null);
    try {
      const query: components['schemas']['ScheduleRequest'] = { reviewed, snapshot_id:term.snapshot_id, term_id:term.term.id,
        selections:selected.map(course => ({ course_id:course.course_id, required:course.required, source:course.source,
          requirement_ids:course.source === 'suggestion' ? course.matches.map(match => match.requirement_id) : [] })),
        preferences, node_budget:100000, result_limit:Number(limit), rule_revisions:ruleRevisions ?? null,
        expected_snapshot_digest:snapshotDigest ?? null };
      const response = await fetch('/api/v1/schedules/generate', {
        method:'POST', signal:requestController.signal, headers:{'Content-Type':'application/json'}, body:JSON.stringify(query),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'Schedules could not be generated.');
      if (!requestController.signal.aborted && current.current === requestKey) setCompleted({ key:requestKey, result:data as Result, request:query });
    } catch (cause) {
      if (!requestController.signal.aborted && current.current === requestKey) setError(cause instanceof Error ? cause.message : 'Could not reach the scheduling service.');
    } finally { if (!requestController.signal.aborted && current.current === requestKey) setBusy(false); }
  }

  return <section className="schedule-panel" aria-labelledby="schedule-title">
    <div className="section-label">PREFERENCES & SECTION OPTIONS <span>Choose the constraints that matter to you</span></div>
    <h2 id="schedule-title">Find section combinations that fit.</h2>
    <p>Required courses must appear in every result. Optional courses can be left out to meet your constraints. Eligibility and seat availability still need verification.</p>
    <form onSubmit={generate}>
      <fieldset><legend>Credit limits and target</legend><div className="schedule-fields">
        <label>Minimum credits<input required type="number" min="0" max="30" step="0.25" value={minimum} onChange={event => setMinimum(event.target.value)} /></label>
        <label>Target credits<input required type="number" min="0" max="30" step="0.25" value={target} onChange={event => setTarget(event.target.value)} /></label>
        <label>Maximum credits<input required type="number" min="0" max="30" step="0.25" value={maximum} onChange={event => setMaximum(event.target.value)} /></label>
      </div><p className="caption">Minimum and maximum are hard limits. The target affects ranking. Credit values come from the imported section combinations.</p></fieldset>
      <fieldset><legend>Meeting restrictions</legend><div className="schedule-fields">
        <label>Earliest class start<input required type="time" value={earliest} onChange={event => setEarliest(event.target.value)} /></label>
        <label>Latest class end<input required type="time" value={latest} onChange={event => setLatest(event.target.value)} /></label>
      </div><p className="caption">Times use Chapel Hill local time. A section with any fixed meeting outside this window is excluded.</p>
      <div className="avoid-days" role="group" aria-label="Days to avoid">{days.map((day,index) => <label key={day}><input type="checkbox" checked={avoided.includes(index)} onChange={event => setAvoided(value => event.target.checked ? [...value,index].sort() : value.filter(item => item !== index))} />Avoid {day}</label>)}</div></fieldset>
      <fieldset><legend>Ranking preferences</legend><div className="schedule-fields"><label>Preferred time of day<select value={preferred} onChange={event => setPreferred(event.target.value as typeof preferred)}><option value="none">No preference</option><option value="morning">Morning (before noon)</option><option value="afternoon">Afternoon (noon or later)</option></select></label><label>Maximum results<select value={limit} onChange={event => setLimit(event.target.value)}><option value="5">5 schedules</option><option value="10">10 schedules</option><option value="20">20 schedules</option></select></label></div><label className="checkbox-label"><input type="checkbox" checked={compact} onChange={event => setCompact(event.target.checked)} />Prefer fewer days with fixed meetings</label><p className="caption">Ranking preferences never override hard restrictions. Unknown/arranged meeting times are excluded; asynchronous courses have no fixed-time conflicts.</p></fieldset>
      <button className="primary" type="submit" disabled={generationDisabled}>{suggestionsLoading ? 'Updating course suggestions…' : busy ? 'Generating schedules…' : 'Generate schedules'}</button>
      {!suggestionsLoading && suggestionsUnavailable && <p role="status">Course suggestions are unavailable. Retry suggestions above before generating schedules with these courses.</p>}
      {selected.length===0 && <p className="caption">Add at least one course above to generate schedules.</p>}
      {selected.length>12 && <p className="notice">This version supports up to 12 selected courses per search. Remove some alternatives before generating schedules.</p>}
    </form>
    {busy && <p role="status">Checking credits, required components and meeting conflicts…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {result && <section className="schedule-results" aria-label="Generated schedules">
      <h3>{result.schedules.length ? `Section combinations (${result.schedules.length})` : 'No schedule found'}</h3>
      <p className="notice"><strong>{result.notice}</strong></p>
      {!result.search_complete && <p className="notice" role="status">Partial search: these are the best results found before the search limit, not a guaranteed global ranking. No result does not prove impossibility.</p>}
      {result.diagnostics.map((diagnostic,index) => <div className="schedule-diagnostic" key={index}><strong>{diagnostic.message}</strong><ul>{diagnostic.suggestions?.map(suggestion => <li key={suggestion}>{suggestion}</li>)}</ul></div>)}
      {result.schedules.length>0 && completed && <ScheduleComparison result={result} request={completed.request} term={term} />}
      <h3>All options ? section details</h3>
      {result.schedules.map((schedule,index) => <article className="schedule-card" key={schedule.id} aria-label={`Schedule option ${index+1}`}>
        <h4>Option {index+1} · {schedule.total_credits} credits</h4><p className="caption">Ranked using your preferences; all hard restrictions are enforced.</p><ul>{schedule.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
        <ScheduleDetails schedule={schedule} />
      </article>)}
      <details><summary>Sections excluded by your constraints</summary>{result.filtered_courses.map(course => <div key={course.course_id}><strong>{course.course_id}: {course.available_bundles} usable combinations</strong><ul>{Object.entries(course.rejected_reasons).map(([reason,count]) => <li key={reason}>{reason.replaceAll('_',' ')}: {count}</li>)}</ul></div>)}</details>
      <details><summary>Planning limits and data sources</summary>{result.warnings.map((warning,index) => <p key={index}>{warning}</p>)}<p>Calendar and exports follow supplied dates and weekly meeting patterns. Verify holidays, cancellations and exam dates separately.</p></details>
    </section>}
  </section>;
}
