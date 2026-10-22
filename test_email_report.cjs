const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const fields={};let copied='',selected=false,message='';
const context=vm.createContext({
  console,Date,Promise,navigator:{},
  document:{execCommand:()=>false},
  $:selector=>fields[selector],esc:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  toast:text=>{message=text},on:()=>{},render:()=>{},
});
vm.runInContext(fs.readFileSync('static/report-dates.js','utf8'),context);
vm.runInContext(fs.readFileSync('static/email-report.js','utf8'),context);
const data={week:'2026-10-19',weekEnd:'2026-10-25',timezone:'America/New_York',includePending:false,students:[
  {name:'Evan Kunkle',total:1.25,rows:[{activity:'PLC <test>',seconds:4500,progress:'Completed — verified',workDate:'2026-10-20',completedAt:Date.parse('2026-10-21T14:00:00Z')/1000,completionStatus:'completed'}]},
  {name:'An Tran',total:0.5,rows:[{activity:'Deployment',seconds:1800,progress:'In process — verified',workDate:'2026-10-21',completedAt:null,completionStatus:'not-completed'}]},
  {name:'Brendan James',total:0,rows:[]},
]};
context.input=data;
const draft=vm.runInContext('formatEmailReport(input)',context);
assert.match(draft.subject,/October 19, 2026.*October 25, 2026/);
for(const name of ['Evan Kunkle','An Tran','Brendan James'])assert.ok(draft.body.includes(name));
assert.match(draft.body,/Combined verified student hours: 1.75/);
assert.match(draft.body,/No verified hours for this week/);
assert.match(draft.body,/Tue, Oct 20, 2026/);assert.match(draft.body,/Completed on: Oct 21, 2026, 10:00 AM EDT/);
assert.match(draft.body,/Completed on: Not completed/);
context.input={...data,includePending:true};
assert.match(vm.runInContext('formatEmailReport(input).body',context),/Unverified time is included/);
vm.runInContext('var state={user:{admin:true}},week="2026-10-19",includePending=false;emailReportDraft=formatEmailReport(input)',context);
const view=vm.runInContext('emailReportView()',context);
assert.match(view,/every registered student account/);assert.match(view,/PLC &lt;test&gt;/);
fields['#email-body']={value:draft.body,disabled:false,focus:()=>{},select:()=>{selected=true}};
(async()=>{
  await vm.runInContext('copyEmailField("#email-body")',context);
  assert.ok(selected);assert.match(message,/Ctrl\+C/);
  context.navigator.clipboard={writeText:async text=>{copied=text}};
  await vm.runInContext('copyEmailField("#email-body")',context);
  assert.equal(copied,draft.body);
  // Late requests must not overwrite a newer report.
  let finishOld,finishNew;context.render=()=>{};
  context.api=()=>new Promise(resolve=>{if(!finishOld)finishOld=resolve;else finishNew=resolve});
  vm.runInContext('var DEMO=false,tab="email";var oldRequest=loadEmailReport();week="2026-10-26";var newRequest=loadEmailReport()',context);
  finishNew({...data,week:'2026-10-26',weekEnd:'2026-11-01'});
  await vm.runInContext('newRequest',context);
  finishOld(data);await vm.runInContext('oldRequest',context);
  assert.match(vm.runInContext('emailReportDraft.subject',context),/October 26/);
  console.log('Email formatting, student sections, HTTP clipboard fallback, and stale-request checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
