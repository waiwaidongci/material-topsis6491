<script setup lang="ts">
import {ref,onMounted,watch,computed} from 'vue';
import {useStudies} from '../stores/studies';
import {useSamples} from '../stores/samples';
import {useAuth} from '../stores/auth';
import {useTask} from '../hooks/useTask';
import {metrics as legacyMetrics,directions,dimensionNames,dimensionHints,formulaFunctions} from '../constants/enums';
import {num} from '../utils/format';
import type {Sample,Criterion,MetricCode,BaseMetric,Dims,CriterionKind,Preview} from '../types/domain';
import PageHeading from '../components/common/PageHeading.vue';
import ErrorNotice from '../components/common/ErrorNotice.vue';
import StudySelect from '../components/StudySelect.vue';
const study=useStudies(),samples=useSamples(),auth=useAuth(),{error,busy,perform}=useTask();
const tab=ref('samples'),ids=ref<number[]>([]),message=ref('');
const editSample=ref<Sample|null>(null),editCriterion=ref<Criterion|null>(null),editMetric=ref<BaseMetric|null>(null);
const codes=Object.keys(legacyMetrics) as MetricCode[];
const extraMetricCodes=computed(()=>study.metrics.map(m=>m.code));
const zeroDims:Dims=[0,0,0,0,0];
const criterionForm=ref({code:'',name:'',unit:'',direction:'benefit',center_weight:1,kind:'base' as CriterionKind,formula:'',dims:[...zeroDims] as Dims,version:null as number|null});
const metricForm=ref({code:'',name:'',unit:'',dims:[...zeroDims] as Dims,version:null as number|null});
const previewSampleCode=ref('');
const dimsText=(d:number[])=>d.map((v,i)=>v?`${dimensionNames[i].split(' ')[0]}^${v}`:'').filter(Boolean).join('·')||'无量纲';
onMounted(()=>perform(async()=>{
  await study.load();
  await Promise.all([samples.load(),study.loadCriteria()]);
  ids.value=[...(study.current?.material_ids||[])];
}));
watch(()=>study.selected,()=>{ids.value=[...(study.current?.material_ids||[])];editCriterion.value=null;editSample.value=null;editMetric.value=null;message.value='';previewSampleCode.value='';});
watch(tab,(t)=>{if(t==='preview')perform(()=>study.loadPreview());});
async function saveSelection(){
  if(!study.current)return;
  await study.save({...study.current,material_ids:ids.value},study.current.id);
  message.value='候选集合已保存；现有结果快照不会被改写。';
}
async function saveSample(e:Event){
  const d=new FormData(e.target as HTMLFormElement),data:Record<string,unknown>=Object.fromEntries(d);
  codes.forEach(k=>{const raw=d.get(k);data[k]=raw===''||raw===null?null:Number(raw);});
  const measurements:Record<string,number|null>={};
  for(const mc of extraMetricCodes.value){
    const raw=d.get('m_'+mc);
    measurements[mc]=raw===''||raw===null?null:Number(raw);
  }
  data.measurements=measurements;
  await samples.save(data,editSample.value?.id);
  editSample.value=null;message.value='试样已保存到全局资料库；基础量变更只重算受影响的派生链。';
}
function openCriterion(c:Criterion|null){
  editCriterion.value=c;
  if(c)criterionForm.value={code:c.code,name:c.name,unit:c.unit,direction:c.direction,center_weight:c.center_weight,kind:c.kind,formula:c.formula,dims:[...c.dims] as Dims,version:c.version};
  else criterionForm.value={code:'',name:'',unit:'',direction:'benefit',center_weight:1,kind:'base',formula:'',dims:[...zeroDims],version:null};
}
async function saveCriterion(e:Event){
  e.preventDefault();
  const f=criterionForm.value;
  const payload={study_id:study.selected,...f,dims:f.dims.map(Number)};
  await study.saveCriterion(payload,editCriterion.value?.id);
  editCriterion.value=null;message.value='指标口径已保存；派生链已按拓扑顺序增量重算，后续新任务使用更新值。';
}
function openMetric(m:BaseMetric|null){
  editMetric.value=m;
  if(m)metricForm.value={code:m.code,name:m.name,unit:m.unit,dims:[...m.dims] as Dims,version:m.version};
  else metricForm.value={code:'',name:'',unit:'',dims:[...zeroDims],version:null};
}
async function saveMetric(e:Event){
  e.preventDefault();
  const f=metricForm.value;
  await study.saveMetric({study_id:study.selected,...f,dims:f.dims.map(Number)},editMetric.value?.id);
  editMetric.value=null;message.value='基础量已保存；量纲用于公式一致性检查。';
}
function insertToken(token:string){criterionForm.value.formula=(criterionForm.value.formula?criterionForm.value.formula+' ':'')+token;}
const refTokens=computed(()=>[...codes,...extraMetricCodes.value,...study.criteria.filter(c=>c.kind==='derived').map(c=>c.code)]);
const previewRows=computed<Preview['samples']>(()=>study.previewData?.samples||[]);
const previewSample=computed(()=>previewRows.value.find(p=>p.code===previewSampleCode.value)||previewRows.value[0]);
watch(previewRows,rows=>{if(rows.length&&!rows.some(r=>r.code===previewSampleCode.value))previewSampleCode.value=rows[0].code;});
function sampleValue(s:Sample,code:string){return codes.includes(code as MetricCode)?(s as unknown as Record<string,number|null>)[code]:s.measurements[code]??null;}
</script>
<template>
<PageHeading no="02" title="试样与口径" sub="研究自定义基础量、单位与量纲；派生指标用公式逐级引用，缺测沿链传播并在预览中说明。"/>
<StudySelect/>
<ErrorNotice :error="error"/>
<p v-if="message" class="success" role="status">{{message}}</p>
<div class="data-tabs">
  <button :class="{active:tab==='samples'}" @click="tab='samples'">材料资料 / {{samples.items.length}}</button>
  <button :class="{active:tab==='base'}" @click="tab='base'">基础量 / {{study.metrics.length+5}}</button>
  <button :class="{active:tab==='criteria'}" @click="tab='criteria'">指标与公式 / {{study.criteria.length}}</button>
  <button :class="{active:tab==='preview'}" @click="tab='preview'">派生预览与排除</button>
</div>

<section v-if="tab==='samples'">
  <div class="section-line"><h2>机构试样资料库</h2>
    <div class="selection-actions"><span>已勾选 {{ids.length}} / {{samples.items.length}} 份</span>
      <button v-if="auth.canEdit" @click="perform(saveSelection)" :disabled="busy">保存候选集合</button></div></div>
  <p class="muted">资料库由各研究共享；固定五项基础量保留原列，研究自定义基础量在右侧“基础量”登记。空白值表示登记缺测，会沿派生链传播。</p>
  <details v-if="auth.canEdit" class="edit-fold" :open="!!editSample">
    <summary>{{editSample?'编辑 '+editSample.code:'＋ 登记材料试样'}}</summary>
    <form :key="editSample?.id||'new'" class="form-grid sample-form" @submit.prevent="e=>perform(()=>saveSample(e))">
      <label>试样编号<input name="code" :value="editSample?.code" required minLength="2"/></label>
      <label>试样名称<input name="name" :value="editSample?.name" required minLength="2"/></label>
      <label>材料类别<input name="family" :value="editSample?.family" required/></label>
      <label>批次<input name="batch" :value="editSample?.batch"/></label>
      <label v-for="key in codes" :key="key">{{legacyMetrics[key].name}} / {{legacyMetrics[key].unit}}
        <input :name="key" type="number" step="any" min="0" :max="key==='absorption'?1:key==='price'?10000:1000" :value="editSample?.[key]??''"/></label>
      <label v-for="mc in study.metrics" :key="mc.code">{{mc.name}} / {{mc.unit}}<small>{{dimsText(mc.dims)}} · 留空=缺测</small>
        <input :name="'m_'+mc.code" type="number" step="any" min="0" :value="editSample?.measurements[mc.code]??''"/></label>
      <div class="button-row"><button class="primary" :disabled="busy">保存试样</button>
        <button v-if="editSample" type="button" @click="editSample=null">取消编辑</button></div>
    </form>
  </details>
  <div class="table-scroll"><table class="sample-table">
    <thead><tr><th>候选</th><th>试样 / 类别</th><th v-for="key in codes" :key="key">{{legacyMetrics[key].name}}<small>{{legacyMetrics[key].unit}}</small></th>
      <th v-for="mc in study.metrics" :key="mc.id">{{mc.name}}<small>{{mc.unit}}</small></th><th v-if="auth.canEdit"/></tr></thead>
    <tbody><tr v-for="s in samples.items" :key="s.id">
      <td><input v-model="ids" type="checkbox" :value="s.id" :disabled="!auth.canEdit" :aria-label="'纳入'+s.code"/></td>
      <td><b>{{s.code}} · {{s.name}}</b><small>{{s.family}} / {{s.batch}}</small></td>
      <td v-for="key in codes" :key="key">{{s[key]==null?'缺测':num(s[key],key==='absorption'?4:3)}}</td>
      <td v-for="mc in study.metrics" :key="mc.id"><span :class="{missing:sampleValue(s,mc.code)==null}">{{sampleValue(s,mc.code)==null?'缺测':num(sampleValue(s,mc.code) as number,3)}}</span></td>
      <td v-if="auth.canEdit"><button class="small-button" @click="editSample=s">编辑</button></td>
    </tr></tbody></table></div>
  <p v-if="!samples.items.length" class="empty">先登记至少两份材料试样，再勾选到研究中。</p>
</section>

<section v-else-if="tab==='base'" class="criterion-spread">
  <div>
    <h2 class="ruled-title">研究基础量 <small>固定五项 + 自定义 {{study.metrics.length}} 项</small></h2>
    <article class="criterion-row metric-row" v-for="(meta,key) in legacyMetrics" :key="key">
      <div><small>{{key}} / {{meta.unit}}</small><h3>{{meta.name}}</h3></div><span class="direction">固定列</span><b>v—</b></article>
    <article class="criterion-row metric-row" v-for="m in study.metrics" :key="m.id">
      <div><small>{{m.code}} / {{m.unit}}</small><h3>{{m.name}} · <i>{{dimsText(m.dims)}}</i></h3></div>
      <span class="direction">自定义</span><b>v{{m.version}}</b>
      <button v-if="auth.canEdit" class="small-button" @click="openMetric(m)">编辑</button></article>
    <aside class="margin-note"><b>量纲怎么登记</b>
      <p v-for="(h,i) in dimensionHints" :key="i">{{h}}</p>
      <p>并发编辑采用版本号乐观锁：他人先保存后，你的旧版本提交会收到409，需刷新后基于最新版本修改。</p></aside>
  </div>
  <form v-if="auth.canEdit" :key="editMetric?.id||'new-metric'" @submit.prevent="e=>perform(()=>saveMetric(e))">
    <h2>{{editMetric?'编辑基础量（代码不可改）':'登记基础量'}}</h2>
    <label>代码（小写字母开头，公式中以此引用）<input name="code" v-model="metricForm.code" required minLength="2" :disabled="!!editMetric" pattern="[a-z][a-z0-9_]+"/></label>
    <label>显示名称<input v-model="metricForm.name" required/></label>
    <label>单位<input v-model="metricForm.unit" required/></label>
    <fieldset class="dims-editor"><legend>五维量纲指数</legend>
      <label v-for="(dn,i) in dimensionNames" :key="dn">{{dn}}<input type="number" step="1" min="-12" max="12" v-model.number="metricForm.dims[i]"/></label>
      <p class="muted">当前：{{dimsText(metricForm.dims)}}</p></fieldset>
    <input type="hidden" name="version" :value="metricForm.version??''"/>
    <button class="primary" :disabled="busy">保存基础量</button>
    <button v-if="editMetric" type="button" @click="editMetric=null">取消</button>
  </form>
</section>

<section v-else-if="tab==='criteria'" class="criterion-spread">
  <div>
    <h2 class="ruled-title">指标方向、公式与中心权重 <small>最多5项</small></h2>
    <article class="criterion-row metric-row" v-for="c in study.criteria" :key="c.id">
      <div><small>{{c.code}} / {{c.unit}} · {{dimsText(c.dims)}} · v{{c.version}}</small>
        <h3>{{c.name}} <i class="kind-tag" :class="c.kind">{{c.kind==='derived'?'派生':'基础'}}</i></h3>
        <p v-if="c.kind==='derived'" class="formula-line">{{c.formula}}</p></div>
      <span :class="['direction',c.direction]">{{directions[c.direction]}}</span><b>{{c.center_weight}}</b>
      <button v-if="auth.canEdit" class="small-button" @click="openCriterion(c)">编辑</button></article>
    <p v-if="!study.criteria.length" class="empty">本研究还未登记指标。从右侧定义基础指标或派生指标。</p>
    <aside class="margin-note"><b>公式与量纲检查</b>
      <p>公式可引用固定五项、本研究基础量与已定义的派生指标；保存时做语法、量纲一致性与循环引用检查，任一不过即422且不写入。</p>
      <p>派生结果必须有限非负；负值、除零、负数开方等会使该试样在此指标被排除，原因在“派生预览”逐条给出。</p></aside>
  </div>
  <form v-if="auth.canEdit" :key="editCriterion?.id||'new-criterion'" @submit.prevent="e=>perform(()=>saveCriterion(e))">
    <h2>{{editCriterion?'编辑指标（代码/类型不可改）':'登记指标口径'}}</h2>
    <label>指标代码<input v-model="criterionForm.code" required minLength="2" :disabled="!!editCriterion" pattern="[a-z][a-z0-9_]+"/></label>
    <label>类型<select v-model="criterionForm.kind" :disabled="!!editCriterion">
      <option value="base">基础量指标 base</option><option value="derived">派生指标 derived</option></select></label>
    <label>显示名称<input v-model="criterionForm.name" required/></label>
    <label>单位<input v-model="criterionForm.unit" required/></label>
    <label>方向<select v-model="criterionForm.direction"><option value="benefit">越大越优 / benefit</option><option value="cost">越小越优 / cost</option></select></label>
    <label>原始中心权重<input v-model.number="criterionForm.center_weight" type="number" step="any" min="0" max="1000" required/></label>
    <template v-if="criterionForm.kind==='derived'">
      <label>公式
        <textarea v-model="criterionForm.formula" rows="2" placeholder="例如 absorption / thickness"></textarea></label>
      <div class="token-strip"><span class="muted">插入：</span>
        <button type="button" class="small-button" v-for="t in refTokens" :key="t" @click="insertToken(t)">{{t}}</button>
        <button type="button" class="small-button" v-for="f in formulaFunctions" :key="f" @click="insertToken(f+'()')">{{f}}</button></div>
      <fieldset class="dims-editor"><legend>声明量纲（须与公式推导一致）</legend>
        <label v-for="(dn,i) in dimensionNames" :key="dn">{{dn}}<input type="number" step="1" min="-12" max="12" v-model.number="criterionForm.dims[i]"/></label>
        <p class="muted">当前：{{dimsText(criterionForm.dims)}}</p></fieldset>
    </template>
    <fieldset v-else class="dims-editor"><legend>量纲指数</legend>
      <label v-for="(dn,i) in dimensionNames" :key="dn">{{dn}}<input type="number" step="1" min="-12" max="12" v-model.number="criterionForm.dims[i]"/></label>
      <p class="muted">当前：{{dimsText(criterionForm.dims)}}</p></fieldset>
    <p class="muted" v-if="editCriterion">提交版本号 v{{criterionForm.version}}；保存冲突说明定义已被他人更新。</p>
    <button class="primary" :disabled="busy">保存口径并增量重算</button>
    <button v-if="editCriterion" type="button" @click="editCriterion=null">取消</button>
  </form>
</section>

<section v-else class="preview-spread">
  <div class="section-line"><h2>逐试样派生推导与排除原因</h2>
    <button v-if="auth.canEdit" class="small-button" @click="perform(()=>study.loadPreview())">刷新预览</button></div>
  <p class="muted">预览读取当前定义实时计算；冻结排队时若存在排除项，整笔任务不会创建（不发布半算结果），排除原因与本页一致。</p>
  <div v-if="!study.previewData" class="empty">加载预览中…</div>
  <template v-else>
    <div class="preview-layout">
      <aside class="preview-list">
        <article v-for="p in previewRows" :key="p.sample_id" :class="['preview-item',{selected:p.code===previewSample?.code,excluded:!!p.exclusions.length}]" @click="previewSampleCode=p.code">
          <b>{{p.code}} · {{p.name}}</b>
          <small v-if="p.exclusions.length">排除 {{p.exclusions.length}} 项：{{p.exclusions.map(x=>x.code).join('、')}}</small>
          <small v-else>全部指标可计算</small>
        </article>
      </aside>
      <div v-if="previewSample" class="preview-detail">
        <h3>{{previewSample.code}} · {{previewSample.name}}</h3>
        <table class="trace-table"><thead><tr><th>指标</th><th>公式</th><th>输入</th><th>结果</th><th>状态/原因</th></tr></thead>
          <tbody>
            <tr v-for="t in previewSample.traces" :key="t.code" :class="{excluded:t.excluded}">
              <td><b>{{t.code}}</b></td><td><code>{{t.formula}}</code></td>
              <td><span v-for="(v,k) in t.inputs" :key="k" class="input-chip">{{k}}={{v==null?'缺测':num(v,4)}}</span></td>
              <td>{{t.value==null?'—':num(t.value,5)}}</td>
              <td><span :class="['direction',t.excluded?'cost':'benefit']">{{t.excluded?t.reason:'纳入权衡'}}</span></td>
            </tr>
          </tbody>
        </table>
        <p v-if="!previewSample.traces.length" class="muted">本研究尚无派生指标。</p>
        <div v-if="previewSample.exclusions.length" class="exclusion-box">
          <b>冻结时将排除该试样</b>
          <p v-for="x in previewSample.exclusions" :key="x.code">{{x.code}}：{{x.reason}}</p>
        </div>
      </div>
    </div>
  </template>
</section>
</template>
