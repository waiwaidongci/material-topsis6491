import {request,post} from './client';
import type {BaseMetric,Measurement,Preview,Criterion} from '../types/domain';
export const list=(study_id:number)=>request<Criterion[]>('/criteria'+`?study_id=${study_id}`);
export const create=(data:unknown)=>post<Criterion>('/criteria',data);
export const update=(id:number,data:unknown)=>request<Criterion>('/criteria/'+id,{method:'PUT',body:JSON.stringify(data)});
export const listMetrics=(study_id:number)=>request<BaseMetric[]>(`/metrics?study_id=${study_id}`);
export const createMetric=(data:unknown)=>post<BaseMetric>('/metrics',data);
export const updateMetric=(id:number,data:unknown)=>request<BaseMetric>('/metrics/'+id,{method:'PUT',body:JSON.stringify(data)});
export const listMeasurements=(study_id:number)=>request<Measurement[]>(`/metrics/measurements?study_id=${study_id}`);
export const setMeasurement=(sample_id:number,metric_code:string,value:number|null)=>
  request<Measurement>(`/metrics/samples/${sample_id}/measurements/${metric_code}`,{method:'PUT',body:JSON.stringify({values:{value}})});
export const preview=(study_id:number)=>request<Preview>(`/metrics/preview?study_id=${study_id}`);
