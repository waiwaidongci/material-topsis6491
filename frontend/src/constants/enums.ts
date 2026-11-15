import type {MetricCode} from '../types/domain';
export const roles={admin:'试样负责人',analyst:'产品研究员',viewer:'研发观察员'};
export const runStatus={queued:'已排队',running:'权重情景演算中',completed:'已完成',failed:'未能计算'};
export const noteStatus={draft:'待负责人审阅',approved:'同意试样验证',rejected:'退回修改'};
export const directions={benefit:'越大越优',cost:'越小越优'};
export const metrics:Record<MetricCode,{name:string;unit:string}>={absorption:{name:'吸声系数',unit:'αw'},impact:{name:'耐冲击',unit:'kJ/m²'},carbon:{name:'碳强度',unit:'kgCO₂e/m²'},price:{name:'单价',unit:'元/m²'},thickness:{name:'厚度',unit:'mm'}};
// Five base dimensions; index matches backend DIMENSION_NAMES.
export const dimensionNames=['长度 L','质量 M','时间 T','电流 I','货币 ¥'];
export const dimensionHints=[
  '厚度:mm→L¹；面积相关量指数为负，如面密度 kg/m² → L⁻²·M¹',
  '质量相关:碳强度 kg/m² → L⁻²·M¹；冲击 kJ/m² → M¹·T⁻²（本册按质量量纲登记）',
  '时间相关量，常规声学测量通常为0',
  '电学量，声学板材料通常为0',
  '价格类:单价 元/m² → L⁻²·¥¹；单位质量价格 元/kg → M⁻¹·¥¹',
];
export const formulaFunctions=['sqrt','log','exp','abs','min','max'];
