import {defineStore} from 'pinia';import {ref,computed} from 'vue';
import * as studies from '../api/studies';
import * as criteriaApi from '../api/criteria';
import type {Study,Criterion,BaseMetric,Preview} from '../types/domain';
export const useStudies=defineStore('studies',()=>{
  const items=ref<Study[]>([]),criteria=ref<Criterion[]>([]),metrics=ref<BaseMetric[]>([]),
    previewData=ref<Preview|null>(null),
    selected=ref(Number(localStorage.getItem('material-study')||1));
  const current=computed(()=>items.value.find(s=>s.id===selected.value));
  async function load(){items.value=await studies.list();if(!items.value.some(s=>s.id===selected.value))selected.value=items.value[0]?.id||0;}
  async function select(id:number){selected.value=id;localStorage.setItem('material-study',String(id));await loadCriteria();}
  async function loadCriteria(){
    if(!selected.value){criteria.value=[];metrics.value=[];previewData.value=null;return;}
    const [cs,ms]=await Promise.all([criteriaApi.list(selected.value),criteriaApi.listMetrics(selected.value)]);
    criteria.value=cs;metrics.value=ms;
  }
  async function loadPreview(){if(selected.value)previewData.value=await criteriaApi.preview(selected.value);}
  async function save(data:unknown,id?:number){const s=id?await studies.update(id,data):await studies.create(data);await load();await select(s.id);return s;}
  async function saveCriterion(data:unknown,id?:number){if(id)await criteriaApi.update(id,data);else await criteriaApi.create(data);await loadCriteria();}
  async function saveMetric(data:unknown,id?:number){if(id)await criteriaApi.updateMetric(id,data);else await criteriaApi.createMetric(data);await loadCriteria();}
  return {items,criteria,metrics,previewData,selected,current,load,select,loadCriteria,loadPreview,save,saveCriterion,saveMetric};
});
