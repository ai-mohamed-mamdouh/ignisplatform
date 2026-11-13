import {useEffect,useRef,useState} from 'react';
import maplibre, {GeoJSONSource} from 'maplibre-gl';
import type {Feature,FeatureCollection} from 'geojson';
import {Crosshair, Layers3, Pentagon, Square, X, Check} from 'lucide-react';
import {countries,useApi,type Filters,type Boundaries,type Detail,type Coord} from './api';
import {localBasemap} from './basemap';
import 'maplibre-gl/dist/maplibre-gl.css';

type Viewport = {bbox:[number,number,number,number];zoom:number};
type Layer = 'detections'|'density'|'tracks';
type MapRow = {id?:string;x:number;y:number;n?:number;sensor?:string};
type MapResponse = {mode:Layer;rows:MapRow[];truncated:boolean};
type Props = {filters:Filters;active:boolean;boundaries?:Boundaries;onRegion:(value?:string)=>void;
  onPolygon:(value?:Coord[])=>void;onDetail:(value:Detail)=>void;focus:Coord|undefined;members:Coord[]};
const empty:FeatureCollection = {type:'FeatureCollection',features:[]};
const geo = (features:Feature[]):FeatureCollection => ({type:'FeatureCollection',features});
const point = (xy:Coord,properties:Record<string,unknown>={}):Feature =>
  ({type:'Feature',geometry:{type:'Point',coordinates:xy},properties});
const mapStyle = import.meta.env.VITE_MAP_STYLE as string|undefined;

export default function ExplorerMap(props:Props) {
  const {filters,active,boundaries,focus,members} = props;
  const element=useRef<HTMLDivElement>(null);
  const map=useRef<maplibre.Map|null>(null);
  const callbacks=useRef(props);
  callbacks.current=props;
  const [loaded,setLoaded]=useState(false);
  const [viewport,setViewport]=useState<Viewport>();
  const [layer,setLayer]=useState<Layer>('detections');
  const [drawing,setDrawing]=useState<'polygon'|'rectangle'>();
  const [vertices,setVertices]=useState<Coord[]>([]);
  const drawRef=useRef(drawing);
  drawRef.current=drawing;
  const [mapError,setMapError]=useState('');
  const data=useApi<MapResponse>('/map/'+layer,viewport&&{...filters,...viewport},loaded&&active&&!!viewport);

  useEffect(()=>{
    const controller=new AbortController();
    let instance:maplibre.Map;
    try {
      instance=new maplibre.Map({container:element.current!,...(mapStyle?{style:mapStyle}:{}),
        center:[134,-26],zoom:3.55,
        minZoom:1,maxZoom:19,renderWorldCopies:false,attributionControl:{compact:true}});
    } catch {
      setMapError('WebGL is unavailable. Enable hardware acceleration to use the map.');
      return;
    }
    map.current=instance;
    instance.addControl(new maplibre.NavigationControl({showCompass:false}),'top-left');
    instance.addControl(new maplibre.ScaleControl({unit:'metric'}),'bottom-left');
    let timer:ReturnType<typeof setTimeout>;
    const capture = () => {
      clearTimeout(timer);

      timer = setTimeout(() => {
        const b = instance.getBounds();
        const rawZoom = instance.getZoom();

        // Normalize coordinates to avoid nearly identical requests.
        const factor = rawZoom < 8 ? 1000 : 100000;

        const bbox: Viewport['bbox'] = [
          Math.floor(Math.max(-180, b.getWest()) * factor) / factor,
          Math.floor(Math.max(-90, b.getSouth()) * factor) / factor,
          Math.ceil(Math.min(180, b.getEast()) * factor) / factor,
          Math.ceil(Math.min(90, b.getNorth()) * factor) / factor
        ];

        const zoom = Math.round(rawZoom * 100) / 100;

        if (bbox[0] >= bbox[2] || bbox[1] >= bbox[3]) {
          return;
        }

        setViewport(previous => {
          if (
            previous &&
            previous.zoom === zoom &&
            previous.bbox.every((value, i) => value === bbox[i])
          ) {
            return previous;
          }

          return { bbox, zoom };
        });
      }, 350);
    };
    instance.on('load',()=>{
      for(const id of ['regions','selection','activity','track-members'])instance.addSource(id,{type:'geojson',data:empty});
      instance.addLayer({id:'region-fill',type:'fill',source:'regions',paint:{'fill-color':'#7eb6d1','fill-opacity':0.09}});
      instance.addLayer({id:'region-outline',type:'line',source:'regions',paint:{'line-color':'#7595ae','line-opacity':0.7}});
      instance.addLayer({id:'selection-fill',type:'fill',source:'selection',paint:{'fill-color':'#2dd4bf','fill-opacity':0.17}});
      instance.addLayer({id:'selection-line',type:'line',source:'selection',paint:{'line-color':'#2dd4bf','line-width':2}});
      instance.addLayer({id:'vertices',type:'circle',source:'selection',filter:['==',['geometry-type'],'Point'],
        paint:{'circle-color':'#2dd4bf','circle-radius':4}});
      instance.addLayer({id:'activity-points',type:'circle',source:'activity',paint:{
        'circle-radius':['case',['has','n'],['interpolate',['linear'],['get','n'],1,4,100,8,10000,18],4],
        'circle-color':['match',['get','kind'],'tracks','#2DD4BF','density','#FF914D','#FFC376'],
        'circle-opacity':0.76,'circle-stroke-width':0.7,'circle-stroke-color':'#182538'}});
      instance.addLayer({id:'track-member-points',type:'circle',source:'track-members',paint:{
        'circle-radius':5,'circle-color':'#2dd4bf','circle-stroke-width':1,'circle-stroke-color':'#fff'}});
      setLoaded(true);setMapError('');capture();
    });
    let basemapLoaded=false;
    instance.once('load',()=>{basemapLoaded=true;});
    const useLocal=()=>localBasemap(controller.signal).then(style=>{
      if(!controller.signal.aborted&&!basemapLoaded)instance.setStyle(style);
    }).catch(()=>{if(!controller.signal.aborted)setMapError('Could not load the local basemap.');});
    const fallback=mapStyle?setTimeout(()=>{if(!basemapLoaded)void useLocal();},4500):undefined;
    if(!mapStyle)void useLocal();
    instance.on('moveend',capture);
    const popup = new maplibre.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12
    });

    let lastHoverAt = 0;

    instance.on('mousemove', event => {
      const now = performance.now();

      // Limit expensive feature queries to around 16 per second.
      if (now - lastHoverAt < 60) return;

      lastHoverAt = now;

      if (!instance.getLayer('activity-points')) return;

      const hit = instance.queryRenderedFeatures(
        event.point,
        { layers: ['activity-points'] }
      )[0];

      instance.getCanvas().style.cursor =
        drawRef.current ? 'crosshair' : hit ? 'pointer' : '';

      if (hit && !drawRef.current) {
        const p = hit.properties;

        const text = p.kind === 'density'
          ? Number(p.n).toLocaleString() + ' thermal detections'
          : p.kind === 'tracks'
          ? 'Candidate ' + p.id + ' · ' + p.n + ' matching detections'
          : p.sensor + ' · ' + p.id;

        popup
          .setLngLat(event.lngLat)
          .setText(text)
          .addTo(instance);

      } else {
        popup.remove();
      }
    });

    instance.on('mouseleave', () => {
      popup.remove();
      instance.getCanvas().style.cursor = '';
    });
    
    instance.on('click',event=>{
      if(drawRef.current){
        const {lng,lat}=event.lngLat.wrap();
        setVertices(previous=>drawRef.current==='rectangle'&&previous.length>=2?[[lng,lat]]:
          previous.length<256?[...previous,[lng,lat]]:previous);
        return;
      }
      if(!instance.getLayer('activity-points'))return;
      const hit=instance.queryRenderedFeatures(event.point,{layers:['activity-points']})[0];
      if(hit?.properties.id) {
        callbacks.current.onDetail({kind:hit.properties.kind,id:String(hit.properties.id)});return;
      }
      if(hit)return;
      const region=instance.queryRenderedFeatures(event.point,{layers:['region-fill']})[0];
      if (region?.id !== undefined && region.id !== null) {
        callbacks.current.onRegion(String(region.id));
      }
    });
    const observer=new ResizeObserver(()=>instance.resize());
    observer.observe(element.current!);
    return()=>{controller.abort();clearTimeout(fallback);clearTimeout(timer);observer.disconnect();popup.remove();instance.remove();map.current=null;};
  },[]);

  const selection=drawing==='rectangle'&&vertices.length===2 ? [
    vertices[0],[vertices[1][0],vertices[0][1]],vertices[1],[vertices[0][0],vertices[1][1]],
  ] as Coord[] : vertices;
  const resetView=()=>{
    const [x,y,zoom]=countries.find(c=>c.code===filters.country)!.center;
    map.current?.jumpTo({center:[x,y],zoom});
  };
  useEffect(()=>{resetView();setDrawing(undefined);setVertices([]);},[filters.country]);
  useEffect(()=>{if(focus)map.current?.easeTo({center:focus,zoom:Math.max(map.current.getZoom(),7)});},[focus]);
  useEffect(()=>{if(loaded)(map.current?.getSource('regions') as GeoJSONSource).setData(boundaries??empty);},[loaded,boundaries]);
  useEffect(()=>{
    if(!loaded)return;
    const features:Feature[]=[];
    const polygon=drawing?selection:filters.polygon;
    if(polygon?.length&&polygon.length>=3)features.push({type:'Feature',properties:{},geometry:{
      type:'Polygon',coordinates:[[...polygon,polygon[0]]]}});
    if(drawing)features.push(...vertices.map(xy=>point(xy)));
    if(!drawing&&filters.region){
      const region=boundaries?.features.find(f=>String(f.id)===filters.region);
      if(region)features.push(region);
    }
    (map.current?.getSource('selection') as GeoJSONSource).setData(geo(features));
  },[loaded,drawing,vertices,filters.polygon,filters.region,boundaries]);
  useEffect(()=>{
    if(loaded)(map.current?.getSource('activity') as GeoJSONSource).setData(geo(active&&data.data?
      data.data.rows.map(row=>point([row.x,row.y],{...row,kind:data.data!.mode})):[]));
  },[loaded,data.data,active]);
  useEffect(()=>{
    if(loaded)(map.current?.getSource('track-members') as GeoJSONSource).setData(geo(members.map(xy=>point(xy))));
  },[loaded,members]);

  function startDrawing(mode:'polygon'|'rectangle'){
    setDrawing(mode);setVertices([]);
  }
  function applySelection(){
    props.onPolygon(selection);setDrawing(undefined);setVertices([]);
  }
  return <section className="map-pane" aria-label="Interactive observation map">
    <div ref={element} className="map-canvas"/>
    <div className="map-tools">
      <button title="Reset map view" aria-label="Reset map view" onClick={resetView}><Crosshair size={17}/></button>
      <button title="Draw polygon" aria-label="Draw polygon" aria-pressed={drawing==='polygon'} onClick={()=>startDrawing('polygon')}><Pentagon size={17}/></button>
      <button title="Draw rectangle" aria-label="Draw rectangle" aria-pressed={drawing==='rectangle'} onClick={()=>startDrawing('rectangle')}><Square size={16}/></button>
      <button title="Clear geographic selection" aria-label="Clear geographic selection" onClick={()=>{setDrawing(undefined);setVertices([]);props.onPolygon(undefined);}}><X size={17}/></button>
    </div>
    <div className="map-layers"><Layers3 size={16}/><select aria-label="Map layer" value={layer} onChange={e=>setLayer(e.target.value as Layer)}>
      <option value="detections">Thermal detections</option><option value="density">Geographic density</option><option value="tracks">Candidate tracks</option>
    </select></div>
    {drawing&&<div className="map-note drawing">Click {drawing==='rectangle'?'two opposite corners':'three or more vertices'}.
      <button disabled={selection.length<3} onClick={applySelection}><Check size={15}/> Apply</button>
      <button onClick={()=>{setDrawing(undefined);setVertices([]);}}>Cancel</button>
    </div>}
    {(mapError||data.error)&&<div className="map-note error" role="alert">{mapError||data.error?.message}</div>}
    {!loaded&&!mapError&&<div className="map-note">Loading basemap…</div>}
    <div className="legend"><i className={data.data?.mode==='tracks'?'teal':''}/>{data.data?.mode==='density'?'Observation density':layer==='tracks'?'Approximate candidate centers':'Thermal observations'}
      {data.isFetching&&' · Updating'}{data.data?.truncated&&' · Zoom in for more results'}</div>
  </section>;
}
