import type {StyleSpecification} from 'maplibre-gl';
import type {FeatureCollection,Geometry,GeoJsonProperties} from 'geojson';
import {feature} from 'topojson-client';
import type {GeometryCollection,Topology} from 'topojson-specification';
import atlasUrl from 'world-atlas/countries-110m.json?url';

export async function localBasemap(signal:AbortSignal):Promise<StyleSpecification> {
  const response=await fetch(atlasUrl,{signal});
  if(!response.ok)throw new Error('Could not read local basemap');
  const topology=await response.json() as Topology<{countries:GeometryCollection}>;
  const data=feature(topology,topology.objects.countries) as FeatureCollection<Geometry,GeoJsonProperties>;
  return {version:8,sources:{world:{type:'geojson',data,attribution:'Natural Earth'}},layers:[
    {id:'ocean',type:'background',paint:{'background-color':'#101e2b'}},
    {id:'land',type:'fill',source:'world',paint:{'fill-color':'#25394a'}},
    {id:'borders',type:'line',source:'world',paint:{'line-color':'#476277','line-width':0.8}},
  ]};
}
