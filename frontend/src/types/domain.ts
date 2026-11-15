export interface User{id:number;name:string;email:string;role:'admin'|'analyst'|'viewer'}
export type MetricCode='absorption'|'impact'|'carbon'|'price'|'thickness';export type Direction='benefit'|'cost';
export type CriterionKind='base'|'derived';
export type Dims=[number,number,number,number,number];
export interface Study{id:number;code:string;name:string;context:string;source_file:string;material_ids:number[]}
export interface Sample{id:number;code:string;name:string;family:string;absorption:number|null;impact:number|null;carbon:number|null;price:number|null;thickness:number|null;batch:string;measurements:Record<string,number|null>}
export interface BaseMetric{id:number;study_id:number;code:string;name:string;unit:string;dims:Dims;version:number}
export interface Measurement{sample_id:number;metric_code:string;value:number|null}
export interface Criterion{id:number;study_id:number;code:string;name:string;unit:string;direction:Direction;center_weight:number;kind:CriterionKind;formula:string;dims:Dims;version:number}
export interface DeriveTrace{code:string;formula:string;value:number|null;inputs:Record<string,number|null>;excluded:boolean;reason:string}
export interface PreviewExclusion{code:string;reason:string}
export interface PreviewSample{sample_id:number;code:string;name:string;values:Record<string,number|null>;traces:DeriveTrace[];exclusions:PreviewExclusion[]}
export interface Preview{criteria:Pick<Criterion,'code'|'name'|'unit'|'kind'|'formula'|'dims'|'version'>[];samples:PreviewSample[];excluded_sample_ids:number[]}
export interface RankRow extends Sample{score:number;rank:number;distance_best:number;distance_worst:number;rank_min:number;rank_max:number;rank_low:number;rank_median:number;rank_high:number;first_share:number;rank_frequency:Record<string,number>;normalized:number[];weighted:number[]}
export interface Draw{repeat:number;weights:number[];scores:number[];ranks:number[];first_share:number[];all_indistinguishable:boolean}
export interface Result{samples:RankRow[];criteria:Criterion[];columns:{index:number;norm:number;constant:boolean;zero_norm:boolean;policy:string}[];center_weights:number[];alpha:number[];concentration:number;repeats:number;seed:number;ideal_best:number[];ideal_worst:number[];all_indistinguishable:boolean;draws:Draw[];zero_weight_scenarios:number;fingerprint:string;scope:string;snapshot:Snapshot}
export interface Snapshot{schema_version?:string;definition_version?:string;study:Study;samples:Sample[];criteria:Criterion[];topological_order?:string[];provenance?:Record<string,Record<string,DeriveTrace>>;excluded?:unknown[];base_metrics?:BaseMetric[]}
export interface RunSummary{id:number;name:string;study_id:number;center_weights:Record<string,number>;concentration:number;repeats:number;seed:number;status:'queued'|'running'|'completed'|'failed';summary:{samples:number;criteria:number;fingerprint?:string;all_indistinguishable?:boolean;definition_version?:string};error:string;created_at:string;definition_version?:string}
export interface Run extends RunSummary{snapshot:Snapshot;result:Result}
export interface Note{id:number;name:string;run_id:number;sample_id:number;protocol:string;status:'draft'|'approved'|'rejected';reviewer_note:string;reviewed_by:string;created_at:string}
