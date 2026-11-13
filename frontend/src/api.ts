import {useQuery} from '@tanstack/react-query';
import type {FeatureCollection} from 'geojson';

export const countries = [
  {code:'AU', name:'Australia', center:[134,-26,3.55]},
  {code:'BR', name:'Brazil', center:[-53,-14,3.4]},
  {code:'ID', name:'Indonesia', center:[118,-3,3.5]},
  {code:'ZA', name:'South Africa', center:[25,-29,4.7]},
] as const;
export const years = [2020,2021,2022,2023,2024,2025];
export const sensors = ['MODIS','VIIRS SNPP','VIIRS JPSS-1'];
export type Country = typeof countries[number]['code'];
export type Coord = [number,number];
export type Filters = {country:Country;year:number;sensor?:string;start?:string;end?:string;region?:string;polygon?:Coord[]};
export type Release = {country:Country;year:number;status:'ready'|'invalid';error?:string;version?:string};
export type Catalog = {ready:boolean;preparation:string|null;releases:Release[]};
export type Boundaries = FeatureCollection;
export type Detail = {kind:'detections'|'tracks';id:string};
export type Row = {day:string;sensor:string;daynight:string|null;n:number};

export async function request<T>(path:string, signal:AbortSignal, body?:unknown):Promise<T> {
  const response = await fetch('/api'+path, body === undefined ? {signal} : {
    signal,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(()=>({}));
    throw new Error(typeof error.detail==='string' ? error.detail :
      Array.isArray(error.detail) ? error.detail.map((item:{msg:string})=>item.msg).join('. ') :
      'Request failed ('+response.status+')');
  }
  return response.json();
}

export function useApi<T>(
  path: string,
  body?: unknown,
  enabled = true
) {
  const isMap = path.startsWith('/map/');

  const isCatalog = [
    '/datasets',
    '/countries',
    '/years'
  ].includes(path);

  return useQuery({
    queryKey: [path, body],

    queryFn: ({ signal }) =>
      request<T>(path, signal, body),

    enabled,

    // Reuse historical analytics instead of refetching
    // whenever a user switches tabs.
    staleTime: isCatalog
      ? 5_000
      : isMap
        ? 20_000
        : 5 * 60_000,

    // Remove unused map requests sooner to save memory.
    gcTime: isMap
      ? 60_000
      : 10 * 60_000,

    // Avoid refetching when returning to the browser tab.
    refetchOnWindowFocus: false,

    // Avoid repeated failed map requests.
    retry: isMap ? 0 : 1
  });
}
