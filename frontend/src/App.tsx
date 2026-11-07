import { useRef, useState, type FormEvent } from 'react';
import type { components } from './api/schema';
import { AuditReview } from './AuditReview';
import { CoursePlanner } from './CoursePlanner';

type Draft = components['schemas']['AuditDraft'];

export function App() {
  const [file, setFile] = useState<File | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [reviewed, setReviewed] = useState<components['schemas']['ReviewedAudit'] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || busy) return;
    setError(''); setDraft(null); setReviewed(null);
    if (file.size > 10 * 1024 * 1024) { setError('Choose a PDF smaller than 10 MB.'); return; }
    setBusy(true);
    try {
      const form = new FormData(); form.append('file', file);
      const response = await fetch('/api/v1/audits/parse', { method: 'POST', body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error?.message || 'The PDF could not be extracted.');
      setDraft(result as Draft);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not reach the parser. Try again.');
    } finally { setBusy(false); }
  }

  function clear() {
    setDraft(null); setReviewed(null); setFile(null); setError('');
    if (input.current) input.current.value = '';
  }

  return <>
    <header className="topbar"><a className="brand" href="/" aria-label="Course Planner home"><span className="brand-mark">C</span><span>CAROLINA <strong>COURSE PLANNER</strong></span></a><span className="badge">Development preview</span></header>
    <main>
      <nav className="steps" aria-label="Planning progress"><span aria-current={!draft ? 'step' : undefined}><b>01</b> Upload Tracker</span><span aria-current={draft && !reviewed ? 'step' : undefined}><b>02</b> Review progress</span><span aria-current={reviewed ? 'step' : undefined}><b>03</b> Plan semester</span></nav>
      <section className="intro"><p className="eyebrow">YOUR NEXT SEMESTER STARTS HERE</p><h1>A clearer path to<br />your next semester.</h1><p className="lede">Start with your Tar Heel Tracker. We’re building a way to turn your degree progress into a schedule that works for you.</p></section>
      <div className="workspace">
        <section className="upload-panel" aria-labelledby="upload-title"><div className="section-label">STEP 01 <span>Read your degree progress</span></div><h2 id="upload-title">Bring your progress with you.</h2><p>Upload a text-based Tracker PDF, then review and correct your course history and degree requirements.</p>
          <form onSubmit={upload}><label className="file-zone" htmlFor="tracker"><span className="file-icon" aria-hidden="true">↥</span><strong>Choose your Tar Heel Tracker</strong><span>PDF · up to 10 MB · up to 25 pages</span><input ref={input} id="tracker" type="file" accept=".pdf,application/pdf" disabled={busy} onChange={e => { setFile(e.target.files?.[0] || null); setDraft(null); setReviewed(null); setError(''); }} /></label>
            <div className="actions"><button className="primary" disabled={!file || busy} type="submit">{busy ? 'Extracting text…' : 'Extract Tracker text'} <span aria-hidden="true">→</span></button>{(file || draft) && <button className="secondary" type="button" disabled={busy} onClick={clear}>Clear session</button>}</div>
          </form>
          <p className="privacy">Your PDF is processed locally by this app’s server and discarded after extraction. Results stay in this tab’s memory; refreshing clears them.</p>
          <div role="status" aria-live="polite">{busy && <p className="notice">Reading your PDF. This can take a few seconds.</p>}</div>
          {error && <p className="error" role="alert">{error}</p>}
        </section>
        <aside className="context-panel"><p className="eyebrow">BUILT AROUND YOUR TRACKER</p><h2>Your requirements.<br />Your starting year.</h2><p>Your entering cohort determines your Gen Ed curriculum. Your Tracker’s listed requirements help identify it, independently of your major.</p><div className="divider" /><h3>What this version does</h3><p>Reads your Tracker, lets you correct your progress, and builds ranked section combinations using clearly labeled semester data.</p><h3>What comes next</h3><p>Validated UNC course and section imports. Current offerings are explicitly fictional sample data.</p><span className="aside-foot">Independent planning tool · Not an official UNC degree audit</span></aside>
      </div>
      {draft && <>
        {draft.review_state === 'needs_review' && <AuditReview original={draft} onReviewChange={setReviewed} />}
        {reviewed && <CoursePlanner key={reviewed.revision} reviewed={reviewed} />}
        <section className="results" aria-labelledby="results-title"><div className="section-label">SOURCE DOCUMENT <span>{draft.page_count} pages</span></div><h2 id="results-title">Your document, ready to inspect.</h2><div className="result-meta"><span className="pill">{draft.support === 'tracker_structure_detected' ? 'Tracker structure detected' : 'Unsupported layout'}</span><span>Reported catalog year: <strong>{draft.curriculum?.reported_catalog_year || 'Not detected'}</strong></span></div><p className="caption">Original text is preserved here so you can compare it with your reviewed details. Course suggestions use the details you confirmed above.</p><details className="parser-notes"><summary>Parser notes ({draft.issues.length})</summary>{draft.issues.map((issue, i) => <p className="notice" key={i}>{issue.page ? `Page ${issue.page}: ` : ''}{issue.message}</p>)}</details><div className="pages">{draft.pages.map(page => <details key={page.number}><summary>Page {page.number}<span>View extracted text</span></summary><pre>{page.text || 'No readable text on this page.'}</pre></details>)}</div></section>
      </>}
      <footer><span>CAROLINA COURSE PLANNER</span><span>One semester. A little more clarity.</span></footer>
    </main>
  </>;
}
