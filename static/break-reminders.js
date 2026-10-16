/* Per-student break reminders; server-owned timing in the live application. */
const breakNotices=new Set();
function demoReminder(mid){
    const intervals=demoState.sessions.filter(s=>s.member===mid&&s.start<=now()).map(s=>[s.start,s.end??now(),s.end===null]).sort((a,b)=>a[0]-b[0]);
    const merged=[];
    for(const x of intervals){const p=merged.at(-1);if(p&&x[0]<=p[1]){p[1]=Math.max(p[1],x[1]);p[2]||=x[2]}else merged.push([...x])}
    const current=merged.findLast(x=>x[2]),settings=demoState.breakSettings??{defaultHours:4,overrides:{}},hours=settings.overrides[mid]??settings.defaultHours;
    const threshold=hours*3600,lead=Math.min(900,threshold/4),elapsed=current?now()-current[0]:0;
    const status=current?(elapsed>=threshold?'due':elapsed>=threshold-lead?'soon':'working'):'idle';
    const snooze=demoState.breakSnoozes?.[mid],snoozed=!!(current&&snooze&&snooze.streakStart===current[0]&&snooze.until>now());
    return {member:mid,streakStart:current?.[0]??null,elapsedSeconds:elapsed,thresholdHours:hours,leadMinutes:lead/60,remainingSeconds:Math.max(0,threshold-elapsed),status,snoozed,snoozedUntil:snoozed?snooze.until:null,notify:['soon','due'].includes(status)&&!snoozed};
}
function demoBreakApi(path,data){
    if(path==='reminders')return {reminders:Object.fromEntries(demoState.members.map(m=>[m.id,demoReminder(m.id)]))};
    if(path==='break-settings'){
        const settings=demoState.breakSettings??={defaultHours:4,overrides:{}};
        if(data.member&&data.reset)delete settings.overrides[data.member];
        else {const h=Number(data.hours);if(!Number.isFinite(h)||h<.25||h>24)throw Error('Hours must be between 0.25 and 24.');if(data.member)settings.overrides[data.member]=h;else settings.defaultHours=h}
        saveDemo();return {ok:true};
    }
    if(path==='snooze-break'){
        const m=data.member,r=demoReminder(m);(demoState.breakSnoozes??={})[m]={streakStart:r.streakStart,until:now()+900};saveDemo();return {ok:true};
    }
}
function breakReminderHTML(r,showWorking=false){
    if(!r||(!r.notify&&!showWorking))return '';
    const name=state.user.admin?memberName(r.member):'You';
    const title=r.status==='due'?'Time for a break':r.status==='soon'?'Your break is coming up':r.status==='idle'?'Ready when you are':'Working time since your last pause';
    const message=r.status==='idle'?'No working task is running. Your next working interval will start a fresh break clock.':`${fmt(r.elapsedSeconds)} of continuous working time · ${r.thresholdHours}-hour break threshold${r.status==='soon'?` · about ${Math.ceil(r.remainingSeconds/60)} minutes to go`:''}.`;
    const own=DEMO||r.member===state.user.member;
    return `<section class="break-card ${r.status==='due'?'break-due':''}" role="${r.notify?'status':'region'}"><div><strong>${esc(name)} · ${esc(title)}</strong><p>${esc(message)}</p>${r.notify?'<p>When you take a break, move all your working cards to <b>In Process (paused)</b>. This reminder does not stop task timers.</p>':''}${r.snoozed?'<p>Reminder snoozed for up to 15 minutes.</p>':''}</div>${r.notify&&own?`<button class="btn small" data-break-snooze="${esc(r.member)}">Remind me in 15 min</button>`:''}</section>`;
}
function renderBreakReminders(){
    const target=$('#break-reminders');if(!target||!state)return;
    const rs=Object.values(state.breakReminders??{}).filter(r=>!member()||r.member===member());
    target.innerHTML=tab==='breaks'?'':rs.filter(r=>r.notify).map(r=>breakReminderHTML(r)).join('');
    const clocks=$('#break-clocks');if(tab==='breaks'&&clocks)clocks.innerHTML=rs.map(r=>breakReminderHTML(r,true)).join('')||'<p class="hint">Break clocks appear once students are assigned work.</p>';
    bindSnoozes();
    // Never send a student's desktop notification to an instructor viewing their account.
    const own=state.breakReminders?.[state.user.member];
    if(own?.notify&&typeof Notification!=='undefined'&&Notification.permission==='granted'){
        const key=[own.member,own.streakStart,own.thresholdHours,own.status].join(':');
        if(!breakNotices.has(key)){
            try{const notification=new Notification('ACETime · '+(own.status==='due'?'Time for a break':'Break coming up'),{body:`You have been working for ${fmt(own.elapsedSeconds)}. Your break threshold is ${own.thresholdHours} hours. Pause your working cards when taking a break.`,tag:'acetime-break',requireInteraction:true});notification.onclick=()=>window.focus();breakNotices.add(key)}catch{/* In-app reminders remain available if desktop notifications are unsupported. */}
        }
    }
}
function breakSettingsView(){
    const settings=state.breakSettings??{defaultHours:4,overrides:{}};
    const rs=Object.values(state.breakReminders??{}).filter(r=>!member()||r.member===member());
    return `<div class="heading"><div><div class="eyebrow">Make room to recharge</div><h1>A reminder to take a break.</h1><p class="sub">Individual reminders based on continuous working time, with overlapping cards counted once.</p></div>${studentSelect()}</div><div class="panel"><h2>Student break clocks</h2><div id="break-clocks">${rs.map(r=>breakReminderHTML(r,true)).join('')||'<p class="hint">Break clocks appear once students are assigned work.</p>'}</div><button class="btn" id="enable-notifications">Enable browser notifications</button><p class="hint">Reminders work while ACETime is open and signed in. Browser notifications require permission and browser support. No email, Slack, or Trello messages are sent. Warnings start up to 15 minutes before the threshold; the break is due at the threshold. Pausing all working tasks ends the current streak.</p>${DEMO?'<button class="btn" id="demo-break">Show a near-4-hour example</button>':''}</div>${state.user.admin?`<section class="panel"><h2>Reminder settings</h2><p class="hint">Set the default for all students, or choose one student for an individual threshold. Saved settings apply immediately.</p><form id="break-settings-form" class="filter"><label>Applies to<select name="member" id="break-student"><option value="">Default for all students</option>${state.members.map(m=>`<option value="${esc(m.id)}">${esc(m.fullName)}</option>`).join('')}</select></label><label>Break after (hours)<input name="hours" id="break-hours" type="number" min="0.25" max="24" step="0.25" value="${settings.defaultHours}" required></label><button class="btn primary">Save reminder</button><button type="button" id="break-reset" class="btn">Use default for selected student</button></form><p class="hint">Current default: ${settings.defaultHours} hours. ${Object.keys(settings.overrides).length} student-specific setting(s).</p></section>`:''}`;
}
function bindSnoozes(){document.querySelectorAll('[data-break-snooze]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('snooze-break',{member:b.dataset.breakSnooze});breakNotices.clear();await pollBreakReminders();if(tab==='breaks')render()}catch(e){toast(e.message)}finally{b.disabled=false}})}
function bindBreakReminders(){
    bindSnoozes();
    on('#enable-notifications','click',async()=>{if(typeof Notification==='undefined')throw Error('This browser does not support desktop notifications. In-app reminders are still active.');if(DEMO&&state.user.admin){toast('Desktop notifications are sent only to a signed-in student in the live app.');return}const permission=await Notification.requestPermission();toast(permission==='granted'?'Browser notifications enabled while ACETime is open.':'In-app reminders remain active.');renderBreakReminders()});
    on('#break-student','change',e=>{const settings=state.breakSettings??{defaultHours:4,overrides:{}};$('#break-hours').value=settings.overrides[e.target.value]??settings.defaultHours});
    on('#break-settings-form','submit',async e=>{e.preventDefault();await api('break-settings',Object.fromEntries(new FormData(e.target)));await refresh();toast('Break reminder saved.')});
    on('#break-reset','click',async()=>{const mid=$('#break-student').value;if(!mid)throw Error('Choose a student first.');await api('break-settings',{member:mid,reset:true});await refresh();toast('Student now uses the default threshold.')});
    on('#demo-break','click',async()=>{const s=demoState.sessions.find(s=>s.member==='an'&&s.end===null);if(s)s.start=now()-3.85*3600;selected='an';saveDemo();await refresh()});
}
let breakPolling=false;
async function pollBreakReminders(){
    if(!state||breakPolling)return;breakPolling=true;
    try{const r=await api('reminders');if(!state)return;state.breakReminders=r.reminders;renderBreakReminders();const status=$('#break-connection-status');if(status)status.textContent='';}
    catch(e){const target=$('#break-reminders');if(target)target.innerHTML='<p id="break-connection-status" class="notice">Break reminders could not refresh. Check your connection.</p>';}
    finally{breakPolling=false}
}
