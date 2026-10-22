function reportWorkDate(row){
  return row.workDate?new Date(row.workDate+'T12:00:00Z').toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}):'Not recorded';
}
function reportCompletedOn(row,timezone){
  if(row.completedAt!==null&&row.completedAt!==undefined)return new Date(row.completedAt*1000).toLocaleString('en-US',{month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short',timeZone:timezone||'America/New_York'});
  return row.completionStatus==='completed'?'Date not recorded':'Not completed';
}
function reportDuration(seconds){
  // Round only the display; all report calculations retain exact seconds.
  const minutes=Math.round(seconds/60);
  return `${Math.floor(minutes/60)}h ${String(minutes%60).padStart(2,'0')}m`;
}
function demoDailyReport(data){
  const rows=[],tz=demoState.timezone||'America/New_York';
  const localDay=t=>new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(t*1000));
  const weekDate=new Date(data.week+'T12:00:00Z');
  if(Number.isNaN(weekDate.getTime())||weekDate.getUTCDay()!==1)throw Error('Choose a Monday for week start.');
  weekDate.setUTCDate(weekDate.getUTCDate()+7);const endDate=weekDate.toISOString().slice(0,10);
  // Find local midnight boundaries by date changes, so preview dates follow Eastern DST too.
  for(const c of demoState.cards){
    const days=new Map();
    for(const s of demoState.sessions.filter(s=>s.card===c.id&&s.member===data.member)){
      const finish=s.end??now(),approved=demoState.confirmations[s.id];
      if(approved===undefined&&!data.includePending)continue;
      const ratio=approved===undefined?1:approved/Math.max(1,finish-s.start);
      let cursor=s.start;
      while(cursor<finish){
        const date=localDay(cursor);let next=finish;
        if(localDay(finish-0.001)!==date){let lo=cursor,hi=Math.min(finish,cursor+90000);while(hi-lo>0.0001){const mid=(lo+hi)/2;if(localDay(mid)===date)lo=mid;else hi=mid;}next=Math.ceil(hi*1000)/1000;}
        if(date>=data.week&&date<endDate){const item=days.get(date)||{seconds:0,verified:true};item.seconds+=(Math.min(next,finish)-cursor)*ratio;item.verified&&=approved!==undefined;days.set(date,item);}
        cursor=next;
      }
    }
    for(const [workDate,item] of days){const progress=Object.entries(labels).find(([k])=>demoState.config.lists[k]===c.idList)?.[1]||'Other';rows.push({activity:c.name,...item,workDate,completedAt:c.completedAt??null,completionStatus:c.idList===demoState.config.lists.done?'completed':'not-completed',progress:progress+(item.verified?' — verified':' — unverified')});}
  }
  rows.sort((a,b)=>a.workDate.localeCompare(b.workDate));
  return {rows,total:rows.reduce((sum,r)=>sum+r.seconds/3600,0),timezone:tz};
}
