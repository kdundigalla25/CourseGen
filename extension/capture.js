// Self-contained so Chrome can serialize this function into an isolated content-script world.
export function captureExpandedSections(termName) {
  const location = window.location;
  if (location.protocol !== 'https:' || location.hostname !== 'pa.cc.unc.edu' || !/^\/ps[pc]\//.test(location.pathname)) {
    return { records:[], errors:['Open the ConnectCarolina class-search page first.'] };
  }
  if (!/^20\d{2} (Spring|Fall|Summer I|Summer II)$/.test(termName)) {
    return { records:[], errors:['Enter the semester exactly, for example 2027 Spring.'] };
  }
  const clean = text => String(text ?? '').replace(/\u00a0/g,' ').replace(/\s+/g,' ').trim();
  const visible = node => {
    if (node.closest('[hidden],[aria-hidden=true],nav,aside,header,footer,script,style')) return false;
    const style = getComputedStyle(node);
    return style.display !== 'none' && style.visibility !== 'hidden' && node.getClientRects().length>0;
  };
  // Only explicit detail labels are exported. Never export whole-page HTML/text or inputs.
  const labels = ['Class Number','Career','Session','Units','Grading','Description','Enrollment Requirements',
    'Class Attributes','Instructor','Dates','Meets','Instruction Mode','Room','Campus','Location','Components',
    'Status','Seats Open','Wait List Open'];
  const elements = [...document.querySelectorAll('div,span,p,dt,dd,td,th,label,h1,h2,h3,h4,h5')];
  const exactLabel = node => clean(node.textContent).replace(/:$/,'') === 'Class Number' && visible(node);
  const anchors = elements.filter(exactLabel).filter(node => ![...node.children].some(exactLabel));
  const headings = elements.filter(node => visible(node) && /^.{1,180}\|\s*[A-Z]{2,5}\s+\d{2,3}[A-Z]?$/.test(clean(node.textContent)));
  const roots = new Set(), records = [], errors = [];
  const escape = text => text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const boundary = labels.map(escape).join('|');
  const value = (text,label) => {
    const matches = [...text.matchAll(new RegExp(`(?:^|\\s)${escape(label)}:\\s*([\\s\\S]*?)(?=\\s(?:${boundary}):|\\s(?:INFORMATION|DETAILS|AVAILABILITY|TEXTBOOKS/COURSE MATERIALS|ADDITIONAL LINKS)\\b|$)`,'g'))];
    if (matches.length>1) throw new Error(`Repeated ${label} fields need a more specific page adapter.`);
    return matches.length ? clean(matches[0][1]) : '';
  };
  const minutes = text => {
    const match = /^(\d{1,2}):(\d{2})\s*([ap]m)$/i.exec(text);
    if (!match || +match[1]<1 || +match[1]>12 || +match[2]>59) throw new Error('Unrecognized meeting time.');
    return (+match[1]%12)*60 + +match[2] + (match[3].toLowerCase()==='pm' ? 720 : 0);
  };
  const date = text => {
    const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
    if (!match) throw new Error('Meeting dates must include the source year.');
    const iso = `${match[3]}-${match[1]}-${match[2]}`;
    const stamp = new Date(`${iso}T00:00:00Z`);
    if (!Number.isFinite(+stamp) || stamp.toISOString().slice(0,10)!==iso) throw new Error('Invalid source date.');
    return iso;
  };
  const count = text => {
    const match = /^(\d+)\s*\/\s*(\d+)$/.exec(text);
    if (!match) return null;
    if (+match[1]>+match[2]) throw new Error('Seat availability exceeds capacity; verify the source labels.');
    return { open:Number(match[1]), capacity:Number(match[2]) };
  };
  for (const anchor of anchors) {
    let root = anchor.parentElement;
    // Stop at the smallest subtree holding both section information and availability.
    while (root && root!==document.body) {
      const text = root.innerText || '';
      const numberCount = [...text.matchAll(/Class Number\s*:/g)].length;
      if (numberCount>1) { root=null; break; }
      if (numberCount===1 && /Components\s*:/.test(text) && /Seats Open\s*:/.test(text) && /\b[A-Z0-9]{3,5}\s*-\s*(?:LEC|LAB|REC|SEM)\s*\(\d+\)/.test(text)) break;
      root=root.parentElement;
    }
    if (!root || root===document.body) { errors.push('Could not isolate one expanded section. Expand its full details and try again.'); continue; }
    if (roots.has(root)) continue;
    roots.add(root);
    try {
      const text = clean(root.innerText);
      if (text.length>30000) throw new Error('Section details exceed the supported size.');
      const classNumber = value(text,'Class Number');
      if (!/^\d+$/.test(classNumber)) throw new Error('A full numeric class number is required.');
      const before = headings.filter(node => !root.contains(node) && (node.compareDocumentPosition(root)&Node.DOCUMENT_POSITION_FOLLOWING));
      const heading = before.at(-1);
      const course = heading && /^(.*?)\|\s*([A-Z]{2,5})\s+(\d{2,3}[A-Z]?)$/.exec(clean(heading.textContent));
      if (!course) throw new Error(`Class ${classNumber}: course heading could not be identified.`);
      // The section summary must precede the details in this subtree.
      const summary = text.slice(0,text.indexOf('Class Number'));
      const section = /\b([A-Z0-9]{3,5})\s*-\s*(LEC|LAB|REC|SEM)\s*\((\d+)\)/.exec(summary);
      if (!section || section[3]!==classNumber) throw new Error(`Class ${classNumber}: expand details with its full section summary visible.`);
      const units = /^(\d+(?:\.\d+)?)\s+units?$/i.exec(value(text,'Units'));
      if (!units) throw new Error(`Class ${classNumber}: credits need verification.`);
      const rawDates = value(text,'Dates');
      const dates = /^(\d{2}\/\d{2}\/\d{4})\s*-\s*(\d{2}\/\d{2}\/\d{4})$/.exec(rawDates);
      const range = dates ? { start_date:date(dates[1]), end_date:date(dates[2]) } : null;
      if (range && range.end_date<range.start_date) throw new Error('Source date range is reversed.');
      const rawMeets = value(text,'Meets');
      const pattern = /^((?:Mo|Tu|We|Th|Fr|Sa|Su)+)\s+(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)$/i.exec(rawMeets);
      const warnings = [];
      let meetings = [{kind:'unknown'}];
      if (pattern && range) {
        const start=minutes(pattern[2]), end=minutes(pattern[3]);
        if (end<=start) throw new Error('Meeting end must be after its start.');
        const tokens=pattern[1].match(/Mo|Tu|We|Th|Fr|Sa|Su/gi).map(day=>day.toLowerCase());
        if (new Set(tokens).size!==tokens.length) throw new Error('Repeated meeting weekdays need verification.');
        meetings=tokens.map(day=>({kind:'timed',weekday:['mo','tu','we','th','fr','sa','su'].indexOf(day),start_minute:start,end_minute:end,...range}));
      } else warnings.push('Meeting pattern or full dates unrecognized; retained as unknown.');
      const seats=count(value(text,'Seats Open')), waitlist=count(value(text,'Wait List Open'));
      if (!seats) warnings.push('Seats Open count was not recognized.');
      const components=value(text,'Components');
      const attributes=value(text,'Class Attributes');
      // Retain source prose; it is not a verified bundle pairing or an automatic Gen Ed mapping.
      records.push({ course_id:`${course[2]} ${course[3]}`, title:clean(course[1]),class_number:classNumber,
        section_number:section[1],component:{LEC:'lecture',LAB:'lab',REC:'recitation',SEM:'seminar'}[section[2]],
        credits:Number(units[1]),term_name:termName,term_verification:'user_entered',
        session:value(text,'Session'),career:value(text,'Career'),meetings,
        instructor:value(text,'Instructor'),room:value(text,'Room'),instruction_mode:value(text,'Instruction Mode'),
        campus:value(text,'Campus'),location:value(text,'Location'),components_text:components,
        enrollment_requirements:value(text,'Enrollment Requirements'),attributes_text:attributes,
        status:value(text,'Status'),seats,waitlist,linkage_status:'unknown',
        raw_meeting_pattern:rawMeets,raw_dates:rawDates,warnings,
        captured_at:new Date().toISOString(),source_origin:location.origin,source_path:location.pathname });
      if (records.length>500) throw new Error('Capture at most 500 expanded sections per page.');
    } catch (cause) { errors.push(cause.message || 'Section could not be parsed.'); }
  }
  if (!anchors.length) errors.push('No expanded section details found. Open a section using its chevron, then capture again.');
  return {records,errors,coverage:'expanded_sections_on_current_page_only'};
}
