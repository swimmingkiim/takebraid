// Optional Node.js smoke test of pure UI handlers with a synthetic DOM; no browser/network access.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, 'blind_review.html'), 'utf8');
const packet = {tasks:[{id:'one',media_id:'m',defect:'focus_failure'},
  {id:'two',media_id:'m',defect:'exposure_failure'}], media:{m:{images:
  [{path:'0.png'},{path:'1.png'},{path:'2.png'}],boundaries_pts:[-40,0,80,120],
  time_base:{numerator:1,denominator:1000}}}};
class Element {
  constructor(){this.value='';this.textContent='';this.checked=false;this.files=[];this.children=[]}
  append(child){this.children.push(child);if(!this.value)this.value=child.value}
  addEventListener(type,fn){this['on'+type]=fn}
  click(){if(this.onclick)this.onclick()}
}
const elements = Object.fromEntries([...html.matchAll(/id="([a-z]+)"/g)].map(m=>[m[1],new Element()]));
elements.packet.textContent=JSON.stringify(packet);
let blob;
const context = vm.createContext({document:{getElementById:id=>elements[id],
  createElement:()=>new Element()},URL:{createObjectURL:value=>{blob=value;return 'blob:unit-test'},
  revokeObjectURL:()=>{}},Blob,setTimeout:fn=>fn()});
const source = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1]
  .replaceAll('__PACKET_SHA256__','a'.repeat(64));
vm.runInContext(source,context);
assert.equal(elements.frame.src,'0.png');
assert.match(elements.timing.textContent,/PTS -40/);
elements.next.onclick();assert.equal(elements.frame.src,'1.png');
assert.match(elements.timing.textContent,/PTS 0/);
elements.reviewer.value='unit-test-simulation';
elements.download.onclick();assert.match(elements.status.textContent,/모든 작업/);
elements.end.value='1';elements.truth.value='normal';elements.add.onclick();
assert.match(elements.ranges.textContent,/\[0, 1\) normal/);
elements.end.value='1';elements.truth.value='defect';elements.add.onclick();
assert.match(elements.status.textContent,/끝 프레임/);
elements.end.value='3';elements.truth.value='unknown';elements.add.onclick();
assert.equal(elements.add.disabled,true);
elements.undo.onclick();assert.equal(elements.first.value,1);
elements.end.value='3';elements.truth.value='defect';elements.add.onclick();
elements.task.value='two';elements.task.onchange();
elements.end.value='3';elements.truth.value='normal';elements.add.onclick();
elements.independent.checked=true;elements.download.onclick();
(async()=>{
  const result=JSON.parse(await blob.text());
  assert.equal(result.packet_sha256,'a'.repeat(64));
  assert.equal(result.independent_before_predictions,true);
  assert.equal(result.tasks[0].intervals[1].truth,'defect');
  assert.equal(result.tasks.length,2);
  elements.draft.onclick();const draft=JSON.parse(await blob.text());
  assert.equal(draft.independent_before_predictions,false);
  elements.restore.files=[{size:100,text:async()=>JSON.stringify(draft)}];
  await elements.restore.onchange();
  assert.equal(elements.independent.checked,false);
  assert.match(elements.status.textContent,/불러왔습니다/);
  draft.packet_sha256='b'.repeat(64);
  elements.restore.files=[{size:100,text:async()=>JSON.stringify(draft)}];
  await elements.restore.onchange();assert.match(elements.status.textContent,/같은 검토 패킷/);
  assert.match(html,/connect-src 'none'/);
  console.log('Synthetic UI handlers passed: signed PTS navigation, interval validation, undo, completion, draft, restore.');
})().catch(error=>{console.error(error);process.exitCode=1});
