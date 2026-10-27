/* Weekly readiness, safe downloads, task filters, and forgotten-timer reminders. */
let boardFilters={query:'',status:'',verification:''},exportMode='detail',productivityRequest=0;
function resetProductivity(){boardFilters={query:'',status:'',verification:''};selected='';report=null;productivityRequest++;}

function boardFilterView(){return `<div class="filter task-filters"><label>Find a task<input type="search" id="task-search" placeholder="Task name or student…" value="${esc(boardFilters.query)}"></label><label>Status<select id="task-status"><option value="">All statuses</option>${Object.entries(labels).map(([key,label])=>`<option value="${key}" ${boardFilters.status===key?'selected':''}>${esc(label)}</option>`).join('')}</select></label><label>Time verification<select id="task-verification">${[['','All tasks'],['unverified','Has unverified time'],['verified','Fully verified'],['empty','No time recorded']].map(([key,label])=>`<option value="${key}" ${boardFilters.verification===key?'selected':''}>${label}</option>`).join('')}</select></label><button class="btn" id="clear-task-filters">Clear filters</button></div>`;}
function filterBoardCards(cards){
  const query=boardFilters.query.trim().toLocaleLowerCase();
  return cards.filter(card=>{
    if(query&&!`${card.name} ${card.idMembers.map(memberName).join(' ')}`.toLocaleLowerCase().includes(query))return false;
    if(boardFilters.status&&card.idList!==state.config?.lists[boardFilters.status])return false;
    const sessions=state.sessions.filter(x=>x.card===card.id&&(!member()||x.member===member()));
    const unverified=sessions.some(x=>!Object.hasOwn(state.confirmations,x.id));
    return !boardFilters.verification||(boardFilters.verification==='empty'?!sessions.length:boardFilters.verification==='unverified'?unverified:sessions.length&&!unverified);
  });
}
function updateBoardResults(rebuild=false){
  const host=$('#task-board');if(!host||!state?.config)return;
  const all=state.cards.filter(c=>!c.closed&&(!member()||c.idMembers.includes(member())||state.sessions.some(s=>s.card===c.id&&s.member===member())));
  const filtered=filterBoardCards(all),status=$('#board-results');
  if(status)status.textContent=`Showing ${filtered.length} of ${all.length} tasks. Time totals follow the student filter.`;
  if(rebuild)host.innerHTML=Object.entries(labels).map(([key,label])=>{
    const cards=filtered.filter(c=>c.idList===state.config.lists[key]);if(key==='done')cards.sort((a,b)=>(b.completedAt||0)-(a.completedAt||0));
    return `<section class="column column-${key}" aria-label="${esc(label)}"><div class="columnhead"><span class="dot"></span><h3>${esc(label)}</h3><span class="count">${cards.length}</span></div>${cards.map(c=>card(c,key)).join('')||'<div class="empty column-empty">No matching tasks</div>'}</section>`;
  }).join('');
  host.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render()});
  host.querySelectorAll('.move').forEach(el=>el.onchange=()=>moveDemo(el.dataset.card,el.value));
}

function renderTimerReminders(){
  const host=$('#timer-reminders');if(!host||!state)return;
  const items=(state.timerReminders||[]).filter(x=>!x.snoozed&&(!member()||x.member===member()));
  host.innerHTML=items.length?`<section class="notice timer-notice" role="status"><strong>Check ${items.length===1?'this long-running timer':`these ${items.length} long-running timers`}.</strong><p>These tasks may have been left running. Pause the task in Trello if you stopped working, then use Time corrections for inaccurate hours. Reminders do not stop timers or change your records.</p><ul>${items.map(x=>`<li><span><strong>${esc(taskName(x.card))}</strong> · ${esc(memberName(x.member))} · ${fmt(x.seconds)} running</span>${x.member===state.user.member?`<button class="btn small" data-timer-snooze="${esc(x.card)}">Remind me in an hour</button>`:''}</li>`).join('')}</ul></section>`:'';
  host.querySelectorAll('[data-timer-snooze]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('timer-snooze',{card:b.dataset.timerSnooze});await pollBreakReminders()}catch(e){toast(e.message)}finally{b.disabled=false}});
}

function productivityView(){
  const backup=tab==='backups';
  return `<div class="heading"><div><div class="eyebrow">${backup?'PROTECT YOUR RECORDS':'CLOSE OUT YOUR WEEK'}</div><h1>${backup?'Database backups':'Your weekly review'}</h1><p class="sub">${backup?'Automatic snapshots of recorded time, accounts, and review history.':'Check what needs attention, then download a report.'}</p></div></div>${backup?'':`<div class="filter review-filter">${studentSelect()}<label>Week starting<input id="review-week" type="date" value="${week}"></label><label>CSV contents<select id="export-format"><option value="detail" ${exportMode==='detail'?'selected':''}>Daily task entries</option><option value="summary" ${exportMode==='summary'?'selected':''}>Student totals</option></select></label><label class="check"><input id="export-pending" type="checkbox" ${includePending?'checked':''}>Include unverified time in download</label><button class="btn primary" id="download-week">${state.user.admin?'Download CSV':'Download my CSV'}</button></div><p class="hint">${state.user.admin?'Choose All students for a class report, or one student for an individual report.':'Your download includes only your own records.'} CSV files open in Excel. Verified hours are included by default.</p>`}<div id="productivity-content" aria-live="polite">Loading…</div>`;
}
async function downloadProductivity(path,data){
  if(DEMO)throw Error('Downloads are available in the connected app.');
  const response=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(!response.ok){let error;try{error=await response.json()}catch{}throw Error(error?.error||'Download failed. Please retry.');}
  const name=response.headers.get('Content-Disposition')?.match(/filename="([a-zA-Z0-9._-]+)"/)?.[1]||'acetime-download';
  const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function loadWeeklyChecklist(){
  const host=$('#productivity-content'),request=++productivityRequest;if(!host)return;
  try{
    const data=await api('weekly-checklist',{week,member:member()});
    if(request!==productivityRequest||tab!=='readiness'||!host.isConnected)return;
    host.innerHTML=`<section class="panel"><div class="sectionhead"><h2>${data.ready?'Ready to share':'Review before sharing'}</h2><span class="badge ${data.ready?'ok':''}">${data.ready?'Checklist complete':'Items need attention'}</span></div><p class="hint">Week of ${esc(data.week)} · ${esc(data.timezone)}. Overlap checks are advisory; a report can still be downloaded while you review outstanding items.</p><ul class="review-checklist">${data.items.map(x=>`<li><span class="check-mark ${x.ok?'complete':''}" aria-hidden="true">${x.ok?'✓':'!'}</span><span>${esc(x.label)}<small>${x.ok?'Complete':`${x.count} ${x.blocking?'item(s) need attention':'overlap(s) to inspect'}`}</small></span><span class="badge ${x.ok?'ok':''}">${x.ok?'Done':x.blocking?'Review':'Advisory'}</span></li>`).join('')}</ul><div class="row"><button class="btn" data-review-tab="verify">Verify time</button><button class="btn" data-review-tab="corrections">Time corrections</button>${state.user.admin?'<button class="btn" id="checklist-sync">Sync history</button>':''}</div></section><section class="panel report-table"><table><thead><tr><th>Student</th><th>Verified hours</th><th>Recorded hours</th></tr></thead><tbody>${data.students.map(x=>`<tr><td>${esc(x.name)}</td><td>${x.verified.toFixed(2)}</td><td>${x.recorded.toFixed(2)}</td></tr>`).join('')||'<tr><td colspan="3">No registered students. Create student accounts in Connections.</td></tr>'}</tbody></table></section>${state.user.admin?`<section class="panel"><h2>Forgotten timer reminders</h2><p class="hint">Flag a task that keeps recording for this many continuous hours. This setting applies to all students; it never stops a task automatically.</p><form id="timer-settings-form" class="filter"><label>Remind after (hours)<input name="hours" type="number" min="0.5" max="72" step="0.5" value="${state.timerSettings?.hours||8}" required></label><button class="btn primary">Save reminder</button></form></section>`:''}`;
    host.querySelectorAll('[data-review-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.reviewTab;render()});
    on('#checklist-sync','click',async e=>{e.target.disabled=true;try{await api('sync');await loadWeeklyChecklist()}finally{e.target.disabled=false}});
    on('#timer-settings-form','submit',async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{await api('timer-settings',Object.fromEntries(new FormData(e.target)));state=await api('state');renderTimerReminders();await loadWeeklyChecklist();toast('Forgotten timer threshold saved.')}finally{button.disabled=false}});
  }catch(e){if(host.isConnected&&request===productivityRequest)host.textContent=e.message;}
}
function backupSize(n){return n>=1048576?(n/1048576).toFixed(1)+' MB':(n/1024).toFixed(1)+' KB';}
async function loadBackups(){
  const host=$('#productivity-content'),request=++productivityRequest;if(!host)return;
  try{
    const data=await api('backups');if(request!==productivityRequest||tab!=='backups'||!host.isConnected)return;
    host.innerHTML=`<section class="panel"><div class="sectionhead"><h2>Automatic database protection</h2><button class="btn primary" id="backup-now">Back up now</button></div><p>Snapshots run every ${data.intervalHours} hours while the server is running. The latest ${data.keep} successful snapshots are retained.</p><p>Last successful backup: <strong>${esc(displayTime(data.lastSuccess))}</strong></p><p>Next attempt: ${esc(displayTime(data.nextAttempt))}</p>${data.error?`<p class="error">${esc(data.error)}</p>`:''}<div class="notice">Snapshots are stored on the application’s persistent storage. Download a copy to keep separately from this server. Restore backups with the app stopped; restoring is an administrator maintenance task.</div></section><section class="panel"><h2>Saved snapshots · ${data.files.length}</h2>${data.files.map(x=>`<article class="pendingrow"><div><h3>${esc(displayTime(x.created))}</h3><p>${esc(x.name)} · ${backupSize(x.bytes)}</p></div><button class="btn" data-backup-download="${esc(x.name)}">Download backup</button></article>`).join('')||'<p>No successful snapshots yet. Use Back up now or wait for the automatic backup worker.</p>'}</section>`;
    on('#backup-now','click',async e=>{e.target.disabled=true;try{await api('backup-now');await loadBackups();toast('Database snapshot created and verified.')}finally{e.target.disabled=false}});
    host.querySelectorAll('[data-backup-download]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await downloadProductivity('backup-download',{name:button.dataset.backupDownload})}catch(e){toast(e.message)}finally{button.disabled=false}});
  }catch(e){if(host.isConnected&&request===productivityRequest)host.textContent=e.message;}
}
function bindProductivity(){
  on('#task-search','input',e=>{boardFilters.query=e.target.value;updateBoardResults(true)});
  on('#task-status','change',e=>{boardFilters.status=e.target.value;updateBoardResults(true)});
  on('#task-verification','change',e=>{boardFilters.verification=e.target.value;updateBoardResults(true)});
  on('#clear-task-filters','click',()=>{boardFilters={query:'',status:'',verification:''};$('#task-search').value='';$('#task-status').value='';$('#task-verification').value='';updateBoardResults(true)});
  if(tab==='readiness'){
    on('#review-week','change',e=>{week=e.target.value;loadWeeklyChecklist()});
    on('#export-format','change',e=>{exportMode=e.target.value});
    on('#export-pending','change',e=>{includePending=e.target.checked});
    on('#download-week','click',async e=>{e.target.disabled=true;try{await downloadProductivity('export',{week,member:member(),scope:state.user.admin&&!member()?'class':'student',format:exportMode,includePending})}finally{e.target.disabled=false}});
    loadWeeklyChecklist();
  }else if(tab==='backups')loadBackups();
}
