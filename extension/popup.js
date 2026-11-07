import { captureExpandedSections } from './capture.js';
const get=id=>document.getElementById(id);
const storageKey='unc-section-preview-v1';
let saved={records:[],captures:[]};
async function load() {
  saved=(await chrome.storage.session.get(storageKey))[storageKey] || {records:[],captures:[]};
  get('summary').textContent=`${saved.records.length} sections collected across ${saved.captures.length} captures.`;
  get('download').disabled=!saved.records.length;
}
get('capture').addEventListener('click',async()=>{
  get('capture').disabled=true;get('errors').replaceChildren();get('status').textContent='Reading expanded class details…';
  try {
    const term=get('term').value.trim();
    if (!/^20\d{2} (Spring|Fall|Summer I|Summer II)$/.test(term)) throw new Error('Enter a semester such as 2027 Spring.');
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    const url=new URL(tab.url || '');
    if(url.protocol!=='https:' || url.hostname!=='pa.cc.unc.edu') throw new Error('Open your ConnectCarolina class-search tab first.');
    const results=await chrome.scripting.executeScript({target:{tabId:tab.id,allFrames:true},func:captureExpandedSections,args:[term]});
    const captures=results.map(r=>r.result).filter(Boolean);
    const records=captures.flatMap(r=>r.records);
    const errors=[...new Set(captures.flatMap(r=>r.errors))];
    // Contradictory duplicates from frames are rejected instead of silently choosing one.
    const index=new Map();
    for (const record of records) {
      const key=`${record.term_name}:${record.class_number}`;
      const prior=index.get(key);
      if(prior && JSON.stringify({...prior,captured_at:''})!==JSON.stringify({...record,captured_at:''})) throw new Error('Conflicting section details found in page frames. Capture one results view at a time.');
      index.set(key,record);
    }
    if(index.size) {
      const merged=new Map(saved.records.map(r=>[`${r.term_name}:${r.class_number}`,r]));
      for(const [key,record] of index) merged.set(key,record);
      if(merged.size>10000) throw new Error('Download and clear this collection before exceeding 10,000 sections.');
      const next={records:[...merged.values()],captures:[...saved.captures,{captured_at:new Date().toISOString(),term_name:term,section_count:index.size,errors,coverage:'expanded_sections_on_current_page_only'}]};
      await chrome.storage.session.set({[storageKey]:next});await load();
    }
    for(const error of errors) {const item=document.createElement('li');item.textContent=error;get('errors').append(item);}
    get('status').textContent=`Captured ${index.size} sections. Only expanded details were inspected.`;
  } catch(error) {get('status').textContent=error.message || 'Capture failed. No new records were saved.';}
  finally {get('capture').disabled=false;}
});
get('download').addEventListener('click',()=>{
  const record={schema_version:'connectcarolina-review-1',adapter_version:'expanded-details-preview-1',
    complete:false,timezone:'America/New_York',...saved,
    limitations:['Semester is entered by the operator; verify it against the active search.',
      'Expanded sections only. No automatic pagination, subject search or complete-result claim.',
      'Seat and waitlist numbers are timestamped open/capacity snapshots, not enrollment guarantees.',
      'Class attribute prose is not an automatic Gen Ed mapping. Component prose does not establish specific section pairings.',
      'Review-only format; not a publishable planner dataset.']};
  const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='connectcarolina-section-review.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
get('clear').addEventListener('click',async()=>{await chrome.storage.session.remove(storageKey);await load();get('status').textContent='Collection cleared.';get('errors').replaceChildren();});
load().catch(()=>{get('status').textContent='Session storage could not be opened.';get('capture').disabled=true;});
