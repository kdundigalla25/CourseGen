import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { components } from './api/schema';
import { clock, events, firstWeek, monday, shiftDate, weekdays } from './calendar';
import { ScheduleDetails } from './ScheduleDetails';
import './calendar.css';
type Result = components['schemas']['ScheduleResult'];
type Request = components['schemas']['ScheduleRequest'];
type Term = components['schemas']['AvailableTerm'];

export function ScheduleComparison({ result, request, term }: { result: Result; request: Request; term: Term }) {
  const [left,setLeft] = useState(0);
  const [right,setRight] = useState('');
  const [week,setWeek] = useState(() => firstWeek(result.schedules,term.term));
  const [preferred,setPreferred] = useState<number | null>(null);
  const [start,setStart] = useState('');
  const [end,setEnd] = useState('');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [detail,setDetail] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { controller.current?.abort(); setBusy(false); setError(''); }, [preferred,start,end]);
  const chosen = preferred === null ? null : result.schedules[preferred];
  const shown = [left,...(right !== '' && Number(right)!==left ? [Number(right)] : [])];
  const allEvents = shown.flatMap(index => events(result.schedules[index],term.term,week));
  const low = Math.floor(Math.min(480,...allEvents.map(e => e.start))/60)*60;
  const high = Math.ceil(Math.max(1080,...allEvents.map(e => e.end))/60)*60;
  const needsDates = chosen?.courses.some(c => c.sections.some(s => s.meetings.some(m => m.kind==='timed' && !(m.start_date || term.term.start_date))));
  const hasTimed = chosen?.courses.some(c => c.sections.some(s => s.meetings.some(m => m.kind==='timed')));
  const optionList = result.schedules.map((s,index) => <option key={s.id} value={index}>Option {index+1} · {s.total_credits} credits</option>);

  async function download(format: 'ics'|'json') {
    if (!chosen || busy) return;
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/v1/schedules/export/${format}`, {
        method:'POST', signal:abort.signal, headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ schedule_request:{ ...request, expected_snapshot_digest:result.snapshot_digest, rule_revisions:result.rule_revisions },
          schedule_id:chosen.id, fallback_start:start || null, fallback_end:end || null }),
      });
      if (!response.ok) { const data = await response.json(); throw new Error(data.error?.message || 'Export failed. Try again.'); }
      const blob = await response.blob();
      if (abort.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href=url; link.download=`preferred-option-${preferred!+1}.${format}`;
      link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
    } catch (cause) { if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : 'Export could not be downloaded.'); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }

  return <section className="comparison" aria-label="Compare schedules">
    <h3>Compare your week</h3>
    <p>Times use Chapel Hill ({result.timezone}). Choose an option as preferred before printing or downloading it. Your choice stays in this session.</p>
    <div className="schedule-fields">
      <label>View option<select value={left} onChange={e => { setLeft(Number(e.target.value)); if (right===e.target.value) setRight(''); setDetail(''); }}>{optionList}</select></label>
      <label>Compare with<select value={right} onChange={e => { setRight(e.target.value); setDetail(''); }}><option value="">No comparison</option>{result.schedules.map((s,index) => index!==left && <option key={s.id} value={index}>Option {index+1} · {s.total_credits} credits</option>)}</select></label>
      <label>Week containing<input type="date" value={week} onChange={e => { setWeek(e.target.value ? monday(e.target.value) : ''); setDetail(''); }} /></label>
    </div>
    <p className="caption">{week ? `Week of ${week}. Classes outside their supplied date range are hidden.` : 'Weekly pattern preview — no calendar dates selected.'} Meetings with missing dates show their weekly pattern. Holidays, cancellations and exams are not inferred. Scroll inside a calendar to see all seven days; select a class for details.</p>
    <div className="calendar-comparison">{shown.map(index => {
      const schedule = result.schedules[index];
      const meetings = events(schedule,term.term,week);
      const asyncCourses = schedule.courses.filter(c => c.sections.some(s => s.meetings.some(m => m.kind==='asynchronous')));
      return <div key={schedule.id} className="calendar-option">
        <h4>Option {index+1} · {schedule.total_credits} credits{preferred===index ? ' · Preferred' : ''}</h4>
        <button type="button" aria-pressed={preferred===index} onClick={() => setPreferred(index)}>Use option {index+1} as preferred</button>
        <div className="calendar-scroll" role="region" aria-label={`Option ${index+1} weekly calendar`} tabIndex={0}>
          <div className="week-calendar"><div className="calendar-head"><span>Time</span>{weekdays.map((day,i) => <span key={day}>{day.slice(0,3)}{week && <small>{shiftDate(week,i).slice(5)}</small>}</span>)}</div>
            <div className="calendar-body" style={{height:(high-low)*1.1}}>
              {Array.from({length:(high-low)/60+1},(_,i) => <div key={i} className="hour-line" style={{top:i*60*1.1}}><span>{clock(low+i*60)}</span></div>)}
              {meetings.map(m => <button type="button" key={m.id} className={`calendar-event course-color-${m.color%6}`} style={{top:(m.start-low)*1.1,height:(m.end-m.start)*1.1,left:`calc(48px + (100% - 48px) * ${m.weekday}/7)`,width:'calc((100% - 48px)/7 - 3px)'}}
                aria-label={`Option ${index+1}: ${m.course}, section ${m.section}, ${weekdays[m.weekday]}, ${clock(m.start)} to ${clock(m.end)}${m.date ? ', '+m.date : ''}. ${m.range}${m.location ? ', '+m.location : ''}`}
                onClick={() => setDetail(`${m.course} · ${m.title} · Section ${m.section} · ${weekdays[m.weekday]} ${clock(m.start)}–${clock(m.end)} · ${m.range}${m.location ? ' · '+m.location : ''}`)}>
                <strong>{m.course}</strong><span>{m.section} · {clock(m.start)}</span>{m.uncertain && <span>Dates unverified</span>}
              </button>)}
            </div>
          </div>
        </div>
        {meetings.length===0 && <p>No fixed meetings in this week.</p>}
        {asyncCourses.length>0 && <p>Asynchronous (no calendar blocks): {asyncCourses.map(c => c.course_id).join(', ')}.</p>}
      </div>;
    })}</div>
    {detail && <p className="notice" role="status">{detail}</p>}
    <p>All options and section details are available in the lists below the export controls.</p>
    <div className="export-controls">
      <h3>{preferred===null ? 'Choose a preferred option to keep' : `Keep preferred option ${preferred+1}`}</h3>
      <p>Print and JSON include every selected section, including asynchronous courses. ICS contains dated fixed meetings only. JSON is a schedule record; importing it to resume a session is not supported.</p>
      {needsDates && <div className="schedule-fields"><label>Calendar start date<input type="date" value={start} onChange={e => setStart(e.target.value)} /></label><label>Calendar end date<input type="date" value={end} onChange={e => setEnd(e.target.value)} /></label><p>Used only where the source has no dates. Verify the actual teaching dates.</p></div>}
      <div className="export-buttons"><button type="button" disabled={!chosen} onClick={() => window.print()}>Print preferred schedule</button>
        <button type="button" disabled={!chosen || busy} onClick={() => void download('json')}>Download schedule JSON</button>
        <button type="button" disabled={!chosen || busy || !hasTimed || (needsDates && (!start || !end || end<start))} onClick={() => void download('ics')}>Download calendar ICS</button></div>
      {chosen && !hasTimed && <p>This option has no fixed meetings to add to a calendar.</p>}
      {busy && <p role="status">Preparing your preferred schedule…</p>}{error && <p role="alert" className="error">{error}</p>}
    </div>
    {chosen && createPortal(<div className="print-sheet"><h1>Preferred option {preferred!+1} · {term.term.name}</h1><p>{result.notice}</p><p>Chapel Hill time ({result.timezone}). {term.term.start_date || start || 'Start date unverified'} through {term.term.end_date || end || 'End date unverified'}.</p><ScheduleDetails schedule={chosen} /><p>Snapshot: {result.snapshot_id} · {result.snapshot_digest}</p><p>Rule versions: {Object.entries(result.rule_revisions).map(([id,revision]) => `${id}: ${revision}`).join('; ')}</p>{result.sources.map(source => <p key={source.id}>Source: {source.id}{source.source_url ? ` · ${source.source_url}` : ''}{source.retrieved_at ? ` · ${source.retrieved_at}` : ''}</p>)}{result.warnings.map((warning,i) => <p key={i}>{warning}</p>)}<p>Verify eligibility, seats and requirement counting. Holidays, cancellations and exams are not inferred.</p></div>,document.body)}
  </section>;
}
