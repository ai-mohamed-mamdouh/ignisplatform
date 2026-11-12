import {useEffect,useRef,useState,type ReactNode} from 'react';
import {init,use,type EChartsCoreOption} from 'echarts/core';
import {BarChart,LineChart,PieChart} from 'echarts/charts';
import {GridComponent,LegendComponent,TooltipComponent} from 'echarts/components';
import {CanvasRenderer} from 'echarts/renderers';
import {useApi,years,type Coord,type Detail,type Filters,type Row} from './api';
import type {Tab} from './App';

use([BarChart,LineChart,PieChart,GridComponent,LegendComponent,TooltipComponent,CanvasRenderer]);
const palette=['#FF914D','#2DD4BF','#79A9F6','#F2C56D','#B796EF','#F17C9B'];
const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const weekdays=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const number=(n:number|null|undefined)=>n==null?'Unavailable':n.toLocaleString(undefined,{maximumFractionDigits:2});
type Props={tab:Tab;filters:Filters;onDay:(day?:string)=>void;onDetail:(item:Detail)=>void;onFocus:(xy:Coord)=>void};
type Count={sensor:string;n:number};
type CalendarRow={day:string;n:number};
type Comparison={year:number;available:boolean;total:number|null;days:number;yoy_pct:number|null;monthly:{month:number;sensor:string;n:number}[]};
type SensorData={stats:(Count&{mean_frp:number|null;frp_percentiles:number[]|null;brightness:number|null})[];
  monthly:{month:string|null;sensor:string;daynight:string|null;n:number;mean_frp:number|null;frp_n:number}[];
  types:(Count&{type:string|null})[];frp_bins:(Count&{bin:number})[]};
type Cells={cells:{x:number;y:number;n:number}[];monthly:{month:string;sensor:string;n:number;cells:number}[]};
type Quality={country:string;year:number;version:string;rows:Record<string,number>;reports:Record<string,number>;features:Record<string,number>;coverage:Record<string,number>;calendar_from_archive:boolean};
const axes={axisLabel:{color:'#A5B5C9'},axisLine:{lineStyle:{color:'#45566C'}},splitLine:{lineStyle:{color:'#2B4057'}}};
const theme={color:palette,textStyle:{color:'#A5B5C9',fontFamily:'Inter, sans-serif'},tooltip:{backgroundColor:'#17263a',borderColor:'#3a536c',textStyle:{color:'#F4F7FB'}}};

function Chart({option,label}:{option:EChartsCoreOption;label:string}){
  const ref=useRef<HTMLDivElement>(null);
  const instance=useRef<ReturnType<typeof init>|null>(null);
  useEffect(()=>{
    const chart=init(ref.current);instance.current=chart;
    const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current!);
    return()=>{observer.disconnect();chart.dispose();instance.current=null;};
  },[]);
  useEffect(()=>instance.current?.setOption({...theme,...option},true),[option]);
  return <div ref={ref} className="chart" role="img" aria-label={label}/>;
}
function Card({title,children}:{title:string;children:ReactNode}){
  return <section className="card"><h3>{title}</h3>{children}</section>;
}
function Trend({title,labels,series,type='bar'}:{title:string;labels:string[];series:{name:string;data:(number|null)[]}[];type?:'bar'|'line'}){
  return <Card title={title}><Chart label={title} option={{
    tooltip:{...theme.tooltip,trigger:'axis',renderMode:'richText'},
    legend:series.length>1?{type:'scroll',textStyle:{color:'#A5B5C9'},bottom:0}:undefined,
    grid:{left:14,right:16,bottom:series.length>1?41:20,top:13,containLabel:true},
    xAxis:{...axes,type:'category',data:labels},yAxis:{...axes,type:'value'},
    series:series.map(s=>({...s,type,showSymbol:false,barMaxWidth:36})),
  }}/></Card>;
}
function totals<T>(rows:T[],key:(row:T)=>string,value:(row:T)=>number){
  const result:Record<string,number>=Object.create(null);
  for(const row of rows){const k=key(row);result[k]=(result[k]??0)+value(row);}
  return result;
}
function State({loading,error}:{loading:boolean;error:Error|null}){
  if(error)return <div className="card error" role="alert">{error.message}</div>;
  if(loading)return <div className="skeleton" role="status">Loading analytics…</div>;
  return null;
}
function Monthly({rows}:{rows:Row[]}){
  const monthly=totals(rows,r=>r.day.slice(5,7),r=>r.n);
  return <Trend title="Monthly activity" labels={months}
    series={[{name:'Thermal detections',data:months.map((_,i)=>monthly[String(i+1).padStart(2,'0')]??0)}]}/>;
}
function Daily({rows}:{rows:Row[]}){
  const daily=totals(rows,r=>r.day,r=>r.n);
  const labels=Object.keys(daily).sort();
  return <Trend title="Daily observation activity" labels={labels} type="line"
    series={[{name:'Thermal detections',data:labels.map(d=>daily[d])}]}/>;
}
function Breakdown({title,values}:{title:string;values:Record<string,number>}){
  return <Card title={title}><Chart label={title} option={{tooltip:{...theme.tooltip,trigger:'item',renderMode:'richText'},
    legend:{type:'scroll',bottom:0,textStyle:{color:'#A5B5C9'}},
    series:[{type:'pie',radius:['43%','71%'],center:['50%','44%'],label:{show:false},
      data:Object.entries(values).map(([name,value])=>({name,value}))}]}}/></Card>;
}
function Overview({filters,onFocus}:Props){
  const query=useApi<{metrics:Record<string,number>;daily:Row[]}>('/analytics/overview',filters);
  const result=query.data;
  const titles={detections:'Thermal detections',tracks:'Candidate tracks',active_days:'Active observation days',
    linked:'Linked detections',unresolved:'Unresolved detections',modis:'MODIS',snpp:'VIIRS SNPP',jpss1:'VIIRS JPSS-1'};
  return <><State loading={query.isPending} error={query.error}/>{result&&<>
    <div className="metrics">{Object.entries(titles).map(([key,title])=><div key={key}><span>{title}</span><strong>{number(result.metrics[key])}</strong></div>)}</div>
    <Monthly rows={result.daily}/><Breakdown title="Sensor distribution" values={totals(result.daily,r=>r.sensor,r=>r.n)}/>
    <Breakdown title="Day / night observations" values={totals(result.daily,r=>r.daynight==='D'?'Day':r.daynight==='N'?'Night':r.daynight??'Unknown',r=>r.n)}/>
    <Daily rows={result.daily}/><Spatial filters={filters} onFocus={onFocus} compact/>
  </>}</>;
}
function Calendar({filters,onDay}:Pick<Props,'filters'|'onDay'>){
  const {start,end,...scope}=filters;
  const query=useApi<CalendarRow[]>('/analytics/calendar',scope);
  const max=Math.max(1,...(query.data??[]).map(r=>r.n));
  const weekday=(new Date(Date.UTC(filters.year,0,1)).getUTCDay()+6)%7;
  const selected=start===end?start:undefined;
  return <Card title={filters.year+' observation calendar'}>
    <div className="section-head"><p>Daily thermal detections · UTC</p>{(start||end)&&<button onClick={()=>onDay()}>Reset dates</button>}</div>
    <State loading={query.isPending} error={query.error}/>
    {query.data&&<><div className="calendar-scroll"><div className="calendar">
      {weekdays.map((day,i)=><span className="week-label" key={day} style={{gridRow:i+2,gridColumn:1}}>{day}</span>)}
      {months.map((name,i)=><span className="month-label" key={name} style={{gridRow:1,gridColumn:Math.floor((weekday+
        (Date.UTC(filters.year,i,1)-Date.UTC(filters.year,0,1))/86400000)/7)+2}}>{name}</span>)}
      {query.data.map((row,i)=>{
        const intensity=row.n===0?0:Math.min(4,1+Math.floor(4*Math.log1p(row.n)/Math.log1p(max)));
        const title=row.day+' · '+number(row.n)+' detections';
        return <button className={'day level-'+intensity} key={row.day} title={title} aria-label={title}
          aria-pressed={selected===row.day} style={{gridRow:(i+weekday)%7+2,gridColumn:Math.floor((i+weekday)/7)+2}}
          onClick={()=>onDay(selected===row.day?undefined:row.day)}/>;
      })}
    </div></div><div className="calendar-key">0{[0,1,2,3,4].map(n=><i key={n} className={'level-'+n}/>)}{number(max)} detections · log scale</div></>}
  </Card>;
}
function YearComparison({filters,onlySensors=false}:{filters:Filters;onlySensors?:boolean}){
  const [selected,setSelected]=useState(years);
  const {start:_,end:__,...scope}=filters;
  const query=useApi<Comparison[]>('/analytics/year-comparison',{...scope,years:selected});
  const rows=query.data??[];
  const sensorNames=[...new Set(rows.flatMap(r=>r.monthly.map(m=>m.sensor)))];
  return <><Card title={onlySensors?'Historical sensor comparison':'Year-over-year comparison'}>
    <p>Full calendar years · shared sensor and geographic filters</p>
    <div className="year-options">{years.map(year=><label key={year}><input type="checkbox" checked={selected.includes(year)}
      disabled={selected.length===1&&selected.includes(year)}
      onChange={()=>setSelected(selected.includes(year)?selected.filter(y=>y!==year):[...selected,year].sort())}/>{year}</label>)}</div>
    <State loading={query.isPending} error={query.error}/>
    {!onlySensors&&query.data&&<div className="table-wrap"><table><thead><tr><th>Year</th><th>Detections</th><th>Per day</th><th>YoY</th></tr></thead>
      <tbody>{rows.map(r=><tr key={r.year}><td>{r.year}</td><td>{number(r.total)}</td><td>{r.total===null?'—':number(r.total/r.days)}</td>
        <td>{r.yoy_pct===null?'—':number(r.yoy_pct)+'%'}</td></tr>)}</tbody></table></div>}
    {onlySensors&&rows.some(r=>!r.available)&&<p>Unavailable: {rows.filter(r=>!r.available).map(r=>r.year).join(', ')}</p>}
  </Card>
  {query.data&&<>
    {!onlySensors&&<><Trend title="Monthly activity across years" labels={months} type="line"
      series={rows.filter(r=>r.available).map(r=>({name:String(r.year),data:months.map((_,i)=>r.monthly.filter(m=>m.month===i+1).reduce((n,m)=>n+m.n,0))}))}/>
      <Trend title="Calendar quarters across years" labels={['Jan–Mar','Apr–Jun','Jul–Sep','Oct–Dec']}
        series={rows.filter(r=>r.available).map(r=>({name:String(r.year),data:[0,1,2,3].map(i=>r.monthly.filter(m=>Math.floor((m.month-1)/3)===i).reduce((n,m)=>n+m.n,0))}))}/></>}
    <Trend title="Annual detections by sensor" labels={rows.map(r=>String(r.year))}
      series={sensorNames.map(sensor=>({name:sensor,data:rows.map(r=>r.available?r.monthly.filter(m=>m.sensor===sensor).reduce((n,m)=>n+m.n,0):null)}))}/>
  </>}</>;
}
function Temporal(props:Props){
  const query=useApi<Row[]>('/analytics/temporal',props.filters);
  const daily=totals(query.data??[],r=>r.day,r=>r.n);
  const high=Object.entries(daily).sort((a,b)=>b[1]-a[1]).slice(0,8);
  const monthly=totals(query.data??[],r=>r.day.slice(5,7),r=>r.n);
  const averaged=months.map((_,i)=>{
    const first=new Date(Date.UTC(props.filters.year,i,1)).toISOString().slice(0,10);
    const last=new Date(Date.UTC(props.filters.year,i+1,0)).toISOString().slice(0,10);
    const start=props.filters.start&&props.filters.start>first?props.filters.start:first;
    const end=props.filters.end&&props.filters.end<last?props.filters.end:last;
    const days=(Date.parse(end)-Date.parse(start))/86400000+1;
    return days>0?(monthly[first.slice(5,7)]??0)/days:null;
  });
  return <><Calendar {...props}/><State loading={query.isPending} error={query.error}/>
    {query.data&&<><Daily rows={query.data}/><Monthly rows={query.data}/>
      <Trend title="Average detections per selected calendar day" labels={months} series={[{name:'Detections per day',data:averaged}]}/>
      <Trend title="Monthly day / night activity" labels={months} type="line" series={['D','N'].map(flag=>{
        const counts=totals(query.data!.filter(r=>r.daynight===flag),r=>r.day.slice(5,7),r=>r.n);
        return {name:flag==='D'?'Day':'Night',data:months.map((_,i)=>counts[String(i+1).padStart(2,'0')]??0)};
      })}/>
      <Card title="Highest-observation days"><div className="rank">{high.map(([day,n])=><button key={day} onClick={()=>props.onDay(day)}>{day}<strong>{number(n)}</strong></button>)}</div></Card></>}
    <YearComparison filters={props.filters}/>
  </>;
}
function Spatial({filters,onFocus,compact=false}:{filters:Filters;onFocus:(xy:Coord)=>void;compact?:boolean}){
  const query=useApi<Cells>('/analytics/spatial',filters);
  const [showRegions,setShowRegions]=useState(false);
  const canCompare=!compact&&!filters.region&&!filters.polygon;
  const regionQuery=useApi<{id:string;name:string;n:number}[]>('/analytics/regions',filters,canCompare&&showRegions);
  const monthly=query.data?.monthly??[];
  const labels=[...new Set(monthly.map(r=>r.month))];
  const names=[...new Set(monthly.map(r=>r.sensor))];
  return <><State loading={query.isPending} error={query.error}/>{query.data&&<>
    {!compact&&<Trend title="Monthly spatial activity by sensor" labels={labels}
      series={names.map(name=>({name,data:labels.map(month=>monthly.find(m=>m.month===month&&m.sensor===name)?.n??0)}))}/>}
    {canCompare&&<Card title="Administrative regions">
      <button onClick={()=>setShowRegions(!showRegions)}>{showRegions?'Hide comparison':'Calculate region comparison'}</button>
      {showRegions&&<><State loading={regionQuery.isPending} error={regionQuery.error}/>
      {regionQuery.data?.length===0&&<p>Administrative boundaries are unavailable.</p>}
      {!!regionQuery.data?.length&&<div className="table-wrap"><table><thead><tr><th>Region</th><th>Detections</th></tr></thead><tbody>
        {regionQuery.data.map(r=><tr key={r.id}><td>{r.name}</td><td>{number(r.n)}</td></tr>)}
      </tbody></table></div>}</>}
    </Card>}
    <Card title={compact?'Geographic activity overview':'Highest-activity grid cells'}>
      <p>0.25° cells · observation counts</p>
      <div className="table-wrap"><table><thead><tr><th>Cell center</th><th>Detections</th></tr></thead><tbody>
        {query.data.cells.slice(0,compact?5:25).map(r=><tr key={r.x+':'+r.y}><td><button onClick={()=>onFocus([r.x+.125,r.y+.125])}>
          {(r.y+.125).toFixed(3)}, {(r.x+.125).toFixed(3)}</button></td><td>{number(r.n)}</td></tr>)}
      </tbody></table></div>
    </Card></>}</>;
}
function Sensors({filters}:Props){
  const query=useApi<SensorData>('/analytics/sensors',filters);
  const data=query.data;
  const labels=[...new Set((data?.monthly??[]).flatMap(r=>r.month?[r.month]:[]))];
  const sensorNames=data?.stats.map(s=>s.sensor)??[];
  const total=data?.stats.reduce((n,s)=>n+s.n,0)??0;
  return <><p className="context">MODIS and VIIRS differ in pixel size, overpass timing and confidence conventions. Counts describe sensor observations.</p>
    <State loading={query.isPending} error={query.error}/>{data&&<>
      <Trend title="Detections by sensor" labels={sensorNames} series={[{name:'Detections',data:data.stats.map(s=>s.n)}]}/>
      <Breakdown title="Contribution by sensor" values={Object.fromEntries(data.stats.map(s=>[s.sensor,s.n]))}/>
      <Trend title="Monthly sensor counts" labels={labels} type="line" series={sensorNames.map(name=>({name,data:labels.map(month=>
        data.monthly.filter(r=>r.month===month&&r.sensor===name).reduce((n,r)=>n+r.n,0))}))}/>
      <Trend title="Day / night by sensor" labels={sensorNames} series={['D','N'].map(flag=>({name:flag==='D'?'Day':'Night',
        data:sensorNames.map(sensor=>data.monthly.filter(r=>r.sensor===sensor&&r.daynight===flag).reduce((n,r)=>n+r.n,0))}))}/>
      <Trend title="Monthly mean FRP by sensor (MW)" labels={labels} type="line" series={sensorNames.map(name=>({name,data:labels.map(month=>
        (() => {
          const samples=data.monthly.filter(r=>r.month===month&&r.sensor===name&&r.frp_n);
          const count=samples.reduce((n,r)=>n+r.frp_n,0);
          return count?samples.reduce((n,r)=>n+(r.mean_frp??0)*r.frp_n,0)/count:null;
        })())}))}/>
      <Trend title="FRP distribution (MW)" labels={['<0','0–<10','10–<50','50–<100','100–<500','≥500']}
        series={sensorNames.map(name=>({name,data:[0,1,2,3,4,5].map(bin=>
          data.frp_bins.find(row=>row.sensor===name&&row.bin===bin)?.n??0)}))}/>
      <Card title="Sensor measurements"><div className="table-wrap"><table><thead><tr><th>Sensor</th><th>Share</th><th>Mean FRP</th><th>FRP p10 / p50 / p90</th><th>Brightness (K)</th></tr></thead>
        <tbody>{data.stats.map(s=><tr key={s.sensor}><td>{s.sensor}</td><td>{number(100*s.n/total)}%</td><td>{number(s.mean_frp)}</td>
          <td>{s.frp_percentiles?.map(number).join(' / ')??'Unavailable'}</td><td>{number(s.brightness)}</td></tr>)}</tbody></table></div>
        <p>FRP percentiles are approximate. Missing FRP values are excluded.</p></Card>
      <Card title="Detection types"><div className="table-wrap"><table><thead><tr><th>Sensor</th><th>Source type</th><th>Detections</th></tr></thead>
        <tbody>{data.types.map(r=><tr key={r.sensor+':'+r.type}><td>{r.sensor}</td><td>{r.type??'Unavailable'}</td><td>{number(r.n)}</td></tr>)}</tbody></table></div></Card>
    </>}<YearComparison filters={filters} onlySensors/></>;
}
function Tracks({filters,onDetail}:Props){
  const q=useApi<{candidate_event_id:string;detections:number;days:number;hours:number|null}[]>('/analytics/tracks',filters);
  const summary=useApi<{metrics:Record<string,number>}>('/analytics/overview',filters);
  return <><p className="context">A candidate track is included when at least one linked detection matches the filters. The table shows matching observations and spans. Map centers are approximate release-level locations.</p>
    <State loading={q.isPending||summary.isPending} error={q.error??summary.error}/>
    {summary.data&&<div className="metrics">{[['tracks','Candidate tracks'],['linked','Linked detections'],['unresolved','Unresolved detections']].map(([k,label])=>
      <div key={k}><span>{label}</span><strong>{number(summary.data!.metrics[k])}</strong></div>)}</div>}
    {q.data&&<Card title="Candidate tracks"><p>Up to 100 tracks ranked by matching detections.</p><div className="table-wrap"><table><thead>
      <tr><th>Track ID</th><th>Detections</th><th>Days</th><th>Span (h)</th></tr></thead><tbody>
      {q.data.map(r=><tr key={r.candidate_event_id}><td><button onClick={()=>onDetail({kind:'tracks',id:r.candidate_event_id})}>{r.candidate_event_id}</button></td>
        <td>{number(r.detections)}</td><td>{r.days}</td><td>{number(r.hours)}</td></tr>)}</tbody></table></div></Card>}</>;
}
function QualityTab({filters}:Props){
  const scope='?country='+filters.country+'&year='+filters.year;
  const query=useApi<Quality>('/quality'+scope);
  const [report,setReport]=useState('');
  const content=useApi<{text:string;truncated:boolean}>('/quality/report'+scope+'&name='+encodeURIComponent(report),undefined,/\.(txt|md|json|csv|ya?ml)$/i.test(report));
  return <><State loading={query.isPending} error={query.error}/>{query.data&&<>
    <Card title={'Release quality · '+query.data.country+' '+query.data.year}><p>Release-wide metadata · version {query.data.version}</p>
      <dl>{Object.entries(query.data.rows).map(([name,n])=><div key={name}><dt>{name}</dt><dd>{number(n)} rows</dd></div>)}</dl>
    </Card><Card title="Tracking coverage">
      <dl>{[['detections','Thermal detections'],['tracks','Candidate tracks'],['linked','Linked detections'],
        ['unresolved','Unresolved detections'],['modis','MODIS'],['snpp','VIIRS SNPP'],['jpss1','VIIRS JPSS-1']].map(([key,label])=>
        <div key={key}><dt>{label}</dt><dd>{number(query.data!.coverage[key])}</dd></div>)}</dl>
      <p>Calendar source · {query.data.calendar_from_archive?'Reconciled release analytics':'Derived from release detections'}</p>
    </Card><Card title="Validation archive"><label>Report<select value={report} onChange={e=>setReport(e.target.value)}>
      <option value="">Select a report</option>{Object.keys(query.data.reports).map(r=><option key={r}>{r}</option>)}</select></label>
      {report&&<p><a href={'/api/quality/download'+scope+'&name='+encodeURIComponent(report)} download>Download selected report</a></p>}
      {report&&/\.(txt|md|json|csv|ya?ml)$/i.test(report)&&<State loading={content.isPending} error={content.error}/>}
      {report&&content.data&&<><pre>{content.data.text}</pre>{content.data.truncated&&<p>Preview limited to 64 KB.</p>}</>}
    </Card><Card title="Scientific interpretation"><p>NASA FIRMS observations identify thermal anomalies. A candidate track links observations algorithmically and requires independent confirmation to establish an individual wildfire. Density measures observation counts per cell. The platform covers historical releases.</p></Card>
  </>}</>;
}
export default function Analytics(props:Props){
  switch(props.tab){
    case 'Overview':return <Overview {...props}/>;
    case 'Temporal':return <Temporal {...props}/>;
    case 'Spatial':return <Spatial filters={props.filters} onFocus={props.onFocus}/>;
    case 'Sensors':return <Sensors {...props}/>;
    case 'Candidate Tracks':return <Tracks {...props}/>;
    case 'Data Quality':return <QualityTab key={props.filters.country+props.filters.year} {...props}/>;
    default:return null;
  }
}
