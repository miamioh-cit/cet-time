const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const reportElement={innerHTML:''};
const context=vm.createContext({console,Date,Intl,Promise,location:{hostname:'localhost'},document:{documentElement:{dataset:{}},querySelector:()=>reportElement},localStorage:{getItem:()=>null},fetch:()=>new Promise(()=>{}),setInterval:()=>{},setTimeout:()=>{},pollBreakReminders:()=>{}});
for(const file of ['report-dates.js','email-report.js','app.js'])vm.runInContext(fs.readFileSync('static/'+file,'utf8'),context);
const completion=Date.parse('2026-10-22T18:00:00Z')/1000;
const input={rows:[{activity:'Expand implementation',progress:'Completed — verified',seconds:2880,verified:true,workDate:'2026-10-20',completedAt:completion,completionStatus:'completed'},{activity:'Short task',progress:'In process — unverified',seconds:360,verified:false,workDate:'2026-10-21',completedAt:null,completionStatus:'not-completed'}],total:0.9,timezone:'America/New_York'};
context.input=input;
vm.runInContext('state={user:{admin:true,member:null},timezone:"America/New_York"};selected="evan";tab="weekly";api=async()=>input',context);
(async()=>{
  await vm.runInContext('loadReport()',context);
  for(const text of ['Work date','Completed on','Tue, Oct 20, 2026','0.80','0h 48m','0.10','0h 06m','Oct 22, 2026, 2:00 PM EDT','Not completed'])assert.ok(reportElement.innerHTML.includes(text),text);
  const combined=vm.runInContext('exportText()',context);assert.equal(combined.split('\t').length,3);assert.ok(combined.includes('Tue, Oct 20, 2026'));assert.ok(combined.includes('Completed on: Oct 22'));
  vm.runInContext('combined=false',context);
  const separate=vm.runInContext('exportText()',context).split('\n');assert.equal(separate.length,2);assert.ok(separate.every(row=>row.split('\t').length===3));
  assert.equal(vm.runInContext('reportCompletedOn({completedAt:null,completionStatus:"completed"})',context),'Date not recorded');
  // Demo sessions split at Eastern midnight, not midnight in the viewer's timezone.
  context.sessions=[{id:'s',card:'c',member:'evan',start:Date.parse('2026-10-21T03:30:00Z')/1000,end:Date.parse('2026-10-21T04:30:00Z')/1000}];
  vm.runInContext('demoState={timezone:"America/New_York",cards:[{id:"c",name:"Task",idList:"done"}],sessions,confirmations:{s:1800},config:{lists:{done:"done"}}}',context);
  const demo=vm.runInContext('demoDailyReport({week:"2026-10-19",member:"evan"})',context);
  assert.deepEqual(Array.from(demo.rows,r=>r.workDate),['2026-10-20','2026-10-21']);assert.ok(Math.abs(demo.total-0.5)<0.00001);assert.ok(demo.rows.every(r=>Math.abs(r.seconds-900)<0.01));
  console.log('Dated weekly table, minute/hour display, completion dates, three-column copy, and demo midnight split passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
