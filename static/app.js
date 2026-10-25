'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="drift-token"]').content;
let currentPlan = null, busy = false, poll = null;
async function api(path, body) {
  const options = {headers: {'X-Drift-Token': token}};
  if (body !== undefined) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
  const res = await fetch('/api/' + path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Request could not finish.');
  return data;
}
function message(text, error = false, working = false) {
  $('status').hidden = !text; $('status').textContent = text;
  $('status').className = 'status' + (error ? ' error' : '') + (working ? ' busy' : '');
}
function node(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n; }
function setBusy(value) { busy = value; for(const id of ['plan','scan','apply','recover','model','intention','excerpts']) $(id).disabled = value; for(const b of document.querySelectorAll('#history-rows button')) b.disabled=value; if(!value){$('plan').disabled=!$('model').value;selectedCount();} }
function clearPlan() { currentPlan = null; $('plan-rows').replaceChildren(); $('approval').hidden = true; $('plan-meta').hidden = true; $('export').hidden = true; $('empty').hidden = false; }
function renderScan(data) {
  $('inventory').replaceChildren(...data.files.map(f => node('span', f.name, 'file-chip')));
  if(!data.files.length) $('inventory').textContent = 'No eligible loose files in this folder.';
  $('skipped-wrap').hidden = !data.skipped.length; $('skipped-count').textContent = data.skipped.length + ' files left out of this batch';
  $('skipped').replaceChildren(...data.skipped.map(f => node('li', f.name + ' — ' + f.reason)));
}
function selectedCount() { const n = document.querySelectorAll('.move-choice:checked').length; $('selected-count').textContent = n + (n === 1 ? ' file selected' : ' files selected'); $('apply').disabled = busy || n === 0; }
function renderPlan(plan) {
  currentPlan = plan; $('empty').hidden = true; $('export').hidden = false; $('plan-meta').hidden = false;
  $('plan-meta').textContent = plan.inference.model + ' · ' + plan.inference.seconds + 's · real local inference · approval expires in 10 minutes';
  $('plan-rows').replaceChildren();
  for(const row of plan.rows) {
    const card = node('article', undefined, 'plan-card'); const check = document.createElement('input'); check.type = 'checkbox'; check.className = 'move-choice'; check.value = row.id; check.checked = false; check.disabled = !row.destination; check.setAttribute('aria-label', 'Approve moving ' + row.name); check.addEventListener('change', selectedCount);
    const text = node('div'); text.append(node('h3', row.name), node('p', row.reason)); text.append(node('div', row.destination ? '↳ ' + row.destination : 'Stays in this folder', 'destination'));
    card.append(check, text, node('span', row.bucket === 'keep' ? 'Keep here' : row.destination.split(/[\\/]/)[1], 'bucket')); $('plan-rows').append(card);
  }
  $('approval').hidden = !plan.rows.some(r => r.destination); selectedCount();
}
function renderHistory(rows) {
  $('history-rows').replaceChildren(); $('history-rows').className = rows.length ? '' : 'history-empty';
  if(!rows.length) $('history-rows').textContent = 'Your move history will appear here. Undo is available after a successful move.';
  for(const row of rows) {
    const item = node('div', undefined, 'history-row'), text = node('div'); text.append(node('strong', row.source), node('small', '↳ ' + row.destination), node('small', row.created + (row.error ? ' · ' + row.error : ''))); item.append(text);
    if(row.state === 'moved') { const b = node('button', 'Undo ↶', 'quiet'); b.disabled = busy; b.addEventListener('click', async () => { try { setBusy(true); renderHistory((await api('undo', {id:row.id})).history); clearPlan(); renderScan(await api('scan',{})); message('Restored ' + row.source + ' to its original place.'); } catch(e) { message(e.message,true); } finally {setBusy(false);} }); item.append(b); }
    else item.append(node('span', row.state, 'history-state'));
    $('history-rows').append(item);
  }
}
async function refresh() { clearPlan(); renderScan(await api('scan', {})); renderHistory((await api('history')).history); }
async function checkJob() {
  try {
    const state = await api('state');
    if(state.busy) return;
    clearInterval(poll); poll = null; setBusy(false);
    if(state.error) {message(state.error,true);return;}
    if(state.plan) {renderPlan(state.plan);message('Your plan is ready. Review the reasons, then select the files you want to move.');}
  } catch(e) { clearInterval(poll); setBusy(false); message(e.message,true); }
}
$('scan').addEventListener('click', async () => { try {setBusy(true);await refresh();message('Folder refreshed. Previous approval cleared.');} catch(e){message(e.message,true);}finally{setBusy(false);} });
$('plan').addEventListener('click', async () => { try {clearPlan();setBusy(true);await api('plan',{model:$('model').value,intention:$('intention').value,excerpts:$('excerpts').checked}); message('The local model is thinking. This can take a few minutes on a laptop. Your files stay put.',false,true); poll=setInterval(checkJob,1500);} catch(e){setBusy(false);message(e.message,true);} });
$('apply').addEventListener('click', async () => { try {const ids = [...document.querySelectorAll('.move-choice:checked')].map(n => n.value); const planId=currentPlan.id;setBusy(true);const result=await api('apply',{plan_id:planId,selected:ids});clearPlan();renderHistory(result.history);message(result.errors.length ? result.moved.length+' moved. Stopped: '+result.errors[0].reason : result.moved.length+' files moved. A little less on your plate.',!!result.errors.length);renderScan(await api('scan',{}));}catch(e){message(e.message,true);}finally{setBusy(false);} });
$('recover').addEventListener('click', async () => {try{renderHistory((await api('recover',{})).history);message('Recovery journal checked. Unresolved records remain visible below.');}catch(e){message(e.message,true);} });
$('export').addEventListener('click', () => {if(!currentPlan)return;const blob=new Blob([JSON.stringify(currentPlan,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download='drift-plan.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
(async () => {
  try {const state=await api('state');$('folder').textContent=state.demo ? 'Sample files · .drift-local / demo-downloads' : state.root;$('mode-note').textContent=state.demo ? 'SAMPLE FOLDER · These files are disposable. Model reasoning and approved moves are real.' : 'YOUR FOLDER · Only loose files in this approved folder are read. Subfolders are left alone.';$('excerpts').checked=state.demo;
    if(state.busy){setBusy(true);message('The local model is still working.',false,true);poll=setInterval(checkJob,1500);}else if(state.plan){renderScan({files:state.plan.rows,skipped:state.plan.skipped});renderPlan(state.plan);renderHistory((await api('history')).history);}else{await refresh();}
    try {const result=await api('models');$('model').replaceChildren(...result.models.map(m=>{const o=node('option',m.name);o.value=m.name;return o;}));if(!result.models.length)throw new Error('No local models installed. Run ollama pull llama3.1:8b, then reload.');}catch(e){$('model').replaceChildren(node('option','Ollama unavailable'));$('plan').disabled=true;message(e.message,true);}
  }catch(e){message(e.message,true);}
})();
