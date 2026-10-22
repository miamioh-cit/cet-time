let emailReportDraft=null,emailReportRequest=0,emailReportStatus='';
function emailDate(iso){return new Date(iso+'T12:00:00Z').toLocaleDateString('en-US',{month:'long',day:'numeric',year:'numeric',timeZone:'UTC'})}
function formatEmailReport(data){
  const range=emailDate(data.week)+' – '+emailDate(data.weekEnd);
  const mode=data.includePending?'Recorded hours (includes unverified time)':'Verified hours';
  const line=s=>String(s??'').replace(/[\r\n\t]+/g,' ');
  const sections=data.students.map(s=>{
    const details=s.rows.length?s.rows.map(r=>`• ${reportWorkDate(r)} | ${line(r.activity)} — ${(r.seconds/3600).toFixed(2)} hours (${reportDuration(r.seconds)}; ${line(r.progress)})\n  Completed on: ${reportCompletedOn(r,data.timezone)}`).join('\n'):(data.includePending?'No recorded hours for this week.':'No verified hours for this week.');
    return `${line(s.name)}\n${mode}: ${s.total.toFixed(2)} hours\n${details}`;
  });
  const total=data.students.reduce((sum,s)=>sum+s.total,0);
  return {subject:`Weekly student time report — ${range}`,body:`Hello,\n\nPlease find the weekly student time report for ${range} below.\nReporting timezone: ${data.timezone}.\n${data.includePending?'Unverified time is included and labeled below; it has not been confirmed.':'Only verified hours are included.'}\n\n${sections.join('\n\n')}\n\nCombined ${data.includePending?'recorded':'verified'} student hours: ${total.toFixed(2)} hours.\nGroup tasks count each student's contribution separately. Entries are split by work date in the reporting timezone. Task statuses and most recent completion dates reflect the current task state. Completion dates that predate tracking may be unavailable.\n\nThank you,`};
}
function emailReportView(){
  const draft=emailReportDraft;
  return `<div class="heading"><div><div class="eyebrow">Ready to share</div><h1>Your weekly email, prepared.</h1><p class="sub">${state.user.admin?'Combine weekly reports for every registered student account.':'Prepare your own weekly report as an email.'}</p></div></div><div class="filter email-filter"><label>Week starting <input id="email-week" type="date" value="${week}"></label><label class="check"><input id="email-pending" type="checkbox" ${includePending?'checked':''}>Include unverified time</label><button class="btn" id="email-generate">Generate email</button></div><p class="hint">Choose a Monday. Uses the same hours and verification rules as Weekly report. Copy the text into Gmail, address it to your professor, and CC your HR contact.</p><div id="email-status" role="status" aria-live="polite">${esc(emailReportStatus)}</div><div class="panel"><section class="email-recipients" aria-label="Email recipients"><h2>Send this report to</h2><div class="email-recipient-row"><label class="field">To<input id="email-to" type="email" value="roseaw@miamioh.edu" readonly></label><button class="btn small" id="email-copy-to">Copy To address</button></div><div class="email-recipient-row"><label class="field">CC<input id="email-cc" type="email" value="franckaw@miamioh.edu" readonly></label><button class="btn small" id="email-copy-cc">Copy CC address</button></div></section><label class="field">Subject<input id="email-subject" value="${esc(draft?.subject||'')}" ${draft?'':'disabled'}></label><button class="btn small" id="email-copy-subject" ${draft?'':'disabled'}>Copy subject</button><label class="field email-body-label">Email body<textarea id="email-body" rows="20" ${draft?'':'disabled'}>${esc(draft?.body||'Generate a report to prepare your email.')}</textarea></label><button class="btn primary" id="email-copy-body" ${draft?'':'disabled'}>Copy email body</button><p class="hint">You can edit the greeting and closing before copying. Generating again replaces those edits. This page prepares text; it does not send email.</p></div>`;
}
function clearEmailDraft(){emailReportRequest++;emailReportDraft=null;emailReportStatus='';}
async function loadEmailReport(){
  const request=++emailReportRequest,reportWeek=week,pending=includePending;
  emailReportDraft=null;emailReportStatus='Preparing email…';
  if(tab==='email')render();
  try{
    let data;
    if(DEMO){
      const date=new Date(reportWeek+'T12:00:00Z');
      if(Number.isNaN(date.getTime())||date.getUTCDay()!==1)throw Error('Choose a Monday for week start.');
      date.setUTCDate(date.getUTCDate()+6);
      const students=await Promise.all(state.members.map(async m=>({name:m.fullName,member:m.id,...await api('report',{member:m.id,week:reportWeek,includePending:pending})})));
      data={week:reportWeek,weekEnd:date.toISOString().slice(0,10),timezone:state.timezone,includePending:pending,students,lastSync:state.lastSync};
    }else data=await api('email-report',{week:reportWeek,includePending:pending});
    if(request!==emailReportRequest||!state)return;
    if(!data.students.length){emailReportStatus='No student accounts are registered. Create student logins in Connections first.';if(tab==='email')render();return;}
    emailReportDraft=formatEmailReport(data);
    const sync=data.lastSync?new Date(data.lastSync*1000).toLocaleString('en-US',{timeZone:data.timezone}):'not recorded';
    emailReportStatus=`Prepared ${data.students.length} student report${data.students.length===1?'':'s'}. Last Trello sync: ${sync} (${data.timezone}).`;
  }catch(error){if(request!==emailReportRequest||!state)return;emailReportStatus=error.message;}
  if(tab==='email'&&state)render();
}
async function copyEmailField(selector){
  const field=$(selector);if(!field||field.disabled)return;
  const value=field.value;
  try{if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(value);toast('Copied. Paste into Gmail.');return;}}catch{}
  field.focus();field.select();
  try{if(document.execCommand('copy')){toast('Copied. Paste into Gmail.');return;}}catch{}
  toast('Text selected. Press Ctrl+C (or Command+C), then paste into Gmail.');
}
function bindEmailReport(){
  on('#email-copy-to','click',()=>copyEmailField('#email-to'));
  on('#email-copy-cc','click',()=>copyEmailField('#email-cc'));
  on('#email-week','change',e=>{week=e.target.value;clearEmailDraft();render();});
  on('#email-pending','change',e=>{includePending=e.target.checked;clearEmailDraft();render();});
  on('#email-generate','click',loadEmailReport);
  on('#email-subject','input',e=>{if(emailReportDraft)emailReportDraft.subject=e.target.value;});
  on('#email-body','input',e=>{if(emailReportDraft)emailReportDraft.body=e.target.value;});
  on('#email-copy-subject','click',()=>copyEmailField('#email-subject'));
  on('#email-copy-body','click',()=>copyEmailField('#email-body'));
}
