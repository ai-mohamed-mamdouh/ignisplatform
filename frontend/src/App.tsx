import {lazy,Suspense,useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Activity,Flame,PanelRightClose,PanelRightOpen,Maximize2,Minimize2,RotateCcw,X,FolderOpen} from 'lucide-react';
import ExplorerMap from './ExplorerMap';
import {countries,request,sensors,useApi,years,type Boundaries,type Catalog,type Filters,type Detail,type Coord} from './api';

const Analytics=lazy(()=>import('./Analytics'));
const tabs=['Overview','Temporal','Spatial','Sensors','Candidate Tracks','Data Quality','AI Insights','Export Report'] as const;
export type Tab=typeof tabs[number];
type Track={metadata:Record<string,unknown>;members:{longitude:number;latitude:number;detection_id:string;sensor:string}[];next:number|null;sensors:{sensor:string;n:number}[]};
const initial:Filters={country:'AU',year:2025};

function DetailCard({detail,filters,onClose,onFocus,onMembers,onTrack}:{
  detail:Detail;filters:Filters;onClose:()=>void;onFocus:(xy:Coord)=>void;
  onMembers:(points:Coord[])=>void;onTrack:(id:string)=>void;
}){
  const [offset,setOffset]=useState(0);
  const route='/'+detail.kind+'/'+encodeURIComponent(detail.id)+'?country='+filters.country+'&year='+filters.year;
  const item=useApi<Record<string,unknown>>(route,undefined,detail.kind==='detections');
  const track=useApi<Track>(route+'&offset='+offset,undefined,detail.kind==='tracks');
  useEffect(()=>{
    if(track.data)onMembers(track.data.members.filter(p=>Number.isFinite(p.longitude)&&Number.isFinite(p.latitude)).map(p=>[p.longitude,p.latitude]));
    return ()=>onMembers([]);
  },[track.data,onMembers]);
  const values=item.data??track.data?.metadata;
  return <section className="card detail">
    <div className="section-head"><div><small>{detail.kind==='tracks'?'CANDIDATE TRACK':'THERMAL DETECTION'}</small><h3>{detail.id}</h3></div>
      <button aria-label="Close details" onClick={onClose}><X size={16}/></button></div>
    {(item.isFetching||track.isFetching)&&<div role="status">Loading details…</div>}
    {(item.error||track.error)&&<div role="alert">{(item.error??track.error)?.message}</div>}
    {values&&<dl>{Object.entries(values).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{value==null?'Unavailable':typeof value==='object'?JSON.stringify(value):String(value)}</dd></div>)}</dl>}
    {typeof item.data?.candidate_event_id==='string'&&<button onClick={()=>onTrack(String(item.data?.candidate_event_id))}>Inspect linked candidate</button>}
    {track.data&&<><p>{track.data.sensors.map(s=>s.sensor+' '+s.n.toLocaleString()).join(' · ')}</p>
      <button onClick={()=>{const p=track.data!.members.find(p=>Number.isFinite(p.longitude)&&Number.isFinite(p.latitude));if(p)onFocus([p.longitude,p.latitude]);}}>Focus observations</button>
      <div className="paging"><button disabled={!offset} onClick={()=>setOffset(offset-100)}>Previous</button>
        <span>{offset+1}–{offset+track.data.members.length}</span>
        <button disabled={track.data.next===null} onClick={()=>setOffset(track.data!.next!)}>Next</button></div></>}
  </section>;
}

export default function App(){
  const [filters,setFilters]=useState<Filters>(initial);
  const [tab,setTab]=useState<Tab>('Overview');
  const [panel,setPanel]=useState<'normal'|'expanded'|'collapsed'>('normal');
  const [detail,setDetail]=useState<Detail>();
  const [focus,setFocus]=useState<Coord>();
  const [members,setMembers]=useState<Coord[]>([]);
  const catalog=useQuery({queryKey:['catalog'],queryFn:({signal})=>request<Catalog>('/datasets',signal),
    refetchInterval:q=>q.state.data?.ready?false:2500,staleTime:0});
  const available=catalog.data?.releases.filter(r=>r.status==='ready')??[];
  const current=available.find(r=>r.country===filters.country&&r.year===filters.year);
  const bounds=useApi<Boundaries>('/regions?country='+filters.country);
  const [initialized,setInitialized]=useState(false);
  useEffect(()=>{
    if(!initialized&&catalog.data?.ready){
      const first=available.find(r=>r.country===filters.country&&r.year===filters.year)??available[0];
      if(first)setFilters({country:first.country,year:first.year});
      setInitialized(true);
    }
  },[initialized,catalog.data,filters.country,filters.year]);
  const change=(next:Filters)=>{setFilters(next);setDetail(undefined);setMembers([]);};
  const patch=(next:Partial<Filters>)=>change({...filters,...next});
  const showDetail=(item:Detail)=>{setDetail(item);if(panel==='collapsed')setPanel('normal');};
  const status=catalog.error?'Connection unavailable':catalog.data?.preparation??(current?'Release ready':'Awaiting dataset');
  const errors=catalog.data?.releases.filter(r=>r.status==='invalid')??[];
  const from=filters.year+'-01-01',until=filters.year+'-12-31';

  return <div className="app">
    <header><div className="identity"><div className="brand-icon"><Flame size={24}/></div><div>
      <h1>Wildfire Intelligence Platform</h1><p>Satellite Thermal Activity &amp; Historical Geospatial Analytics</p></div></div>
      <div className="status"><Activity size={15}/><span>{status}</span></div></header>
    <div className="filters" aria-label="Observation filters">
      <label>Country<select aria-label="Country" value={filters.country} onChange={e=>{
        const country=e.target.value as Filters['country'];
        const year=available.find(r=>r.country===country&&r.year===filters.year)?.year??
          available.filter(r=>r.country===country).at(-1)?.year??filters.year;
        change({country,year,sensor:filters.sensor});
      }}>{countries.map(c=><option key={c.code} value={c.code}>{c.name}</option>)}</select></label>
      <label>Year<select aria-label="Year" value={filters.year} onChange={e=>patch({year:Number(e.target.value),start:undefined,end:undefined})}>
        {years.map(y=><option key={y} value={y}>{y}{available.some(r=>r.country===filters.country&&r.year===y)?'':' · unavailable'}</option>)}</select></label>
      <label>From UTC<input type="date" min={from} max={filters.end??until} value={filters.start??''} onChange={e=>patch({start:e.target.value||undefined})}/></label>
      <label>To UTC<input type="date" min={filters.start??from} max={until} value={filters.end??''} onChange={e=>patch({end:e.target.value||undefined})}/></label>
      <label>Sensor<select aria-label="Sensor" value={filters.sensor??''} onChange={e=>patch({sensor:e.target.value||undefined})}>
        <option value="">All sensors</option>{sensors.map(s=><option key={s}>{s}</option>)}</select></label>
      <label>Region<select aria-label="Region" value={filters.region??(filters.polygon?'@custom':'')} onChange={e=>patch({region:e.target.value||undefined,polygon:undefined})}>
        <option value="">Entire country</option>{filters.polygon&&<option value="@custom" disabled>Custom selection</option>}
        {bounds.data?.features.map(f=><option key={f.id} value={f.id}>{f.properties?.name}</option>)}</select></label>
      <button className="reset" onClick={()=>change({country:filters.country,year:filters.year})}><RotateCcw size={15}/> Reset filters</button>
    </div>
    <main className={'workspace '+panel}>
      <ExplorerMap filters={filters} active={!!current} boundaries={bounds.data} onDetail={showDetail}
        onRegion={region=>patch({region,polygon:undefined})} onPolygon={polygon=>patch({region:undefined,polygon})}
        focus={focus} members={members}/>
      {panel==='collapsed'?<aside className="collapsed-panel"><button aria-label="Open analytics" onClick={()=>setPanel('normal')}><PanelRightOpen size={18}/></button></aside>:
        <aside className="analytics-pane" aria-label="Analytics panel">
          <div className="panel-top"><h2>Analytics</h2><div>
            <button title={panel==='expanded'?'Restore panel':'Expand panel'} aria-label={panel==='expanded'?'Restore panel':'Expand panel'}
              onClick={()=>setPanel(panel==='expanded'?'normal':'expanded')}>{panel==='expanded'?<Minimize2 size={16}/>:<Maximize2 size={16}/>}</button>
            <button title="Collapse analytics" aria-label="Collapse analytics" onClick={()=>setPanel('collapsed')}><PanelRightClose size={18}/></button>
          </div></div>
          <nav aria-label="Analytics sections">{tabs.map(name=><button key={name} aria-current={tab===name?'page':undefined} onClick={()=>setTab(name)}>{name}</button>)}</nav>
          <div className="panel-body">
            {detail&&current&&<DetailCard key={detail.kind+detail.id} detail={detail} filters={filters} onClose={()=>setDetail(undefined)}
              onFocus={setFocus} onMembers={setMembers} onTrack={id=>showDetail({kind:'tracks',id})}/>}
            {tab==='AI Insights'||tab==='Export Report'?<section className="card"><h3>{tab==='AI Insights'?'AI-Powered Insights — Coming Soon':'Comprehensive Reporting — Coming Soon'}</h3></section>:
              current?<Suspense fallback={<div className="skeleton" role="status">Loading analytics…</div>}><Analytics
                key={tab} tab={tab} filters={filters} onDay={day=>patch({start:day,end:day})}
                onDetail={showDetail} onFocus={setFocus}/></Suspense>:
              <div className="empty">
                <div className="empty-icon"><FolderOpen size={25}/></div>
                <h3>{catalog.error?'Analytics unavailable':!catalog.data?.ready?'Preparing datasets':available.length?'Release unavailable':'No datasets installed'}</h3>
                <p>{catalog.error?catalog.error.message:!catalog.data?.ready?status:available.length?
                  'Choose a country and year with a validated release.':'Add NASA FIRMS releases to the data directory to begin exploring historical thermal activity.'}</p>
                {catalog.error&&<button onClick={()=>catalog.refetch()}>Retry</button>}
                {errors.map(r=><div className="release-error" key={r.country+r.year}><b>{r.country} {r.year}</b><p>{r.error}</p></div>)}
              </div>}
          </div>
        </aside>}
    </main>
    <footer><span>NASA FIRMS · Historical observations</span><span>UTC · 2020–2025</span></footer>
  </div>;
}
