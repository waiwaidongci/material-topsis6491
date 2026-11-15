from sqlalchemy import select,func
from fastapi import HTTPException
from src.models import Criterion,BaseMetric
from src.services.study_service import get_study
from src.services.derivation.graph import GraphError,validate_definition,downstream
from src.services.derivation.formula import FormulaError,dependencies,parse
from src.services.derivation.dimensions import is_valid_dims
from src.services import derivation_service as derived
from sqlalchemy import select


def list_criteria(db,study_id):
    return db.scalars(select(Criterion).where(Criterion.study_id==study_id).order_by(Criterion.code)).all()


def _base_catalog(db,study_id):
    """Research-defined base quantities usable in formulas (code -> dims)."""
    metrics=db.scalars(select(BaseMetric).where(BaseMetric.study_id==study_id)).all()
    catalog={m.code:tuple(m.dims) for m in metrics}
    # Legacy five columns are always available as base quantities.
    catalog.setdefault('absorption',(0,0,0,0,0));catalog.setdefault('impact',(0,1,0,0,0))
    catalog.setdefault('carbon',(1,1,0,0,0));catalog.setdefault('price',(1,0,0,0,1))
    catalog.setdefault('thickness',(1,0,0,0,0))
    return catalog


def _definition_payload(data):
    return {'code':data.code,'kind':data.kind,'formula':data.formula or '','dims':list(data.dims)}


def _check_count(db,study_id,adding):
    count=db.scalar(select(func.count()).select_from(Criterion).where(Criterion.study_id==study_id))
    if adding and count>=5:
        raise HTTPException(422,'每项研究最多5个指标（基础量与派生指标合计）')


def validate(db,data,id=None):
    get_study(db,data.study_id)
    if not is_valid_dims(data.dims):
        raise HTTPException(422,'量纲须为5个整数指数（length,mass,time,current,currency）')
    if db.scalar(select(Criterion).where(
        Criterion.study_id==data.study_id,Criterion.code==data.code,Criterion.id!=(id or 0))):
        raise HTTPException(409,'研究已有该指标代码')
    others=[{'code':c.code,'kind':c.kind,'formula':c.formula or '','dims':list(c.dims)}
            for c in list_criteria(db,data.study_id) if c.id!=(id or 0)]
    base_catalog=_base_catalog(db,data.study_id)
    # Merge base-quantity dimensions so formula dimension inference sees them.
    for code,dim in base_catalog.items():
        if not any(o['code']==code for o in others):
            others.append({'code':code,'kind':'base','formula':'','dims':list(dim)})
    try:
        node,refs,inferred=validate_definition(
            data.code,data.kind,data.formula or '',others,set(base_catalog))
    except (GraphError,FormulaError) as exc:
        raise HTTPException(422,str(exc))
    if data.kind=='derived' and inferred is not None and list(inferred)!=list(data.dims):
        raise HTTPException(422,f'声明量纲与公式推导量纲不一致：公式得到 {list(inferred)}')
    return refs


def create_criterion(db,data):
    _check_count(db,data.study_id,adding=True)
    validate(db,data)
    item=Criterion(study_id=data.study_id,code=data.code,name=data.name,unit=data.unit,
                   direction=data.direction,center_weight=data.center_weight,
                   kind=data.kind,formula=(data.formula or '') if data.kind=='derived' else '',
                   dims=list(data.dims),version=1)
    db.add(item);db.flush()
    if data.kind=='derived':
        derived.recompute_study(db,data.study_id,only_codes={data.code})
    db.commit()
    return item


def update_criterion(db,id,data):
    item=db.get(Criterion,id)
    if not item:raise HTTPException(404,'指标不存在')
    if data.version is None:
        raise HTTPException(428,'缺少版本号，无法进行并发编辑校验')
    if item.version!=data.version:
        raise HTTPException(409,'指标定义已被他人修改，请刷新后基于最新版本编辑')
    if item.study_id!=data.study_id:raise HTTPException(422,'不能迁移指标所属研究')
    if item.code!=data.code:raise HTTPException(422,'指标代码是引用键，不能修改；请新建指标')
    # kind changes would invalidate the meaning of cached rows and references.
    if item.kind!=data.kind:raise HTTPException(422,'不能在基础量与派生指标之间转换类型')
    validate(db,data,id)
    all_criteria=[{'code':c.code,'kind':c.kind,'formula':c.formula or '','dims':list(c.dims)}
                  for c in list_criteria(db,data.study_id)]
    # Any base-definition edit touches every derived chain depending on it; a
    # formula edit additionally refreshes the edited derived criterion itself.
    chain=downstream(all_criteria,{item.code})
    affected=chain | ({item.code} if item.kind=='derived' else set())
    item.name,item.unit,item.direction=data.name,data.unit,data.direction
    item.center_weight=data.center_weight
    item.dims=list(data.dims)
    if item.kind=='derived':
        item.formula=data.formula or ''
    item.version+=1
    db.flush()
    # Only the impacted derived chain is invalidated and recomputed.
    derived.invalidate_for(db,data.study_id,affected)
    derived.recompute_study(db,data.study_id,only_codes=affected)
    db.commit()
    return item
