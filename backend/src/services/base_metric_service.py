from sqlalchemy import select
from fastapi import HTTPException
from src.models import BaseMetric, Criterion
from src.services.study_service import get_study
from src.services.derivation.dimensions import is_valid_dims
from src.services.derivation.formula import FormulaError, parse, infer_dimensions, dependencies
from src.services.derivation.graph import GraphError, topological_order

LEGACY_BASE = {
    'absorption': {'name': '吸声系数', 'unit': 'αw', 'dims': [0, 0, 0, 0, 0]},
    'impact': {'name': '耐冲击', 'unit': 'kJ/m²', 'dims': [0, 1, 0, 0, 0]},
    'carbon': {'name': '碳强度', 'unit': 'kgCO₂e/m²', 'dims': [1, 1, 0, 0, 0]},
    'price': {'name': '单位面积价格', 'unit': '元/m²', 'dims': [1, 0, 0, 0, 1]},
    'thickness': {'name': '厚度', 'unit': 'mm', 'dims': [1, 0, 0, 0, 0]},
}


def list_base_metrics(db, study_id):
    get_study(db, study_id)
    return db.scalars(select(BaseMetric).where(BaseMetric.study_id == study_id).order_by(BaseMetric.code)).all()


def get_base_metric(db, study_id, code):
    return db.scalar(select(BaseMetric).where(BaseMetric.study_id == study_id, BaseMetric.code == code))


def _conflict(db, study_id, code, exclude_id=0):
    return db.scalar(select(BaseMetric).where(
        BaseMetric.study_id == study_id, BaseMetric.code == code, BaseMetric.id != exclude_id))


def create_base_metric(db, data):
    get_study(db, data.study_id)
    if not is_valid_dims(data.dims):
        raise HTTPException(422, '量纲须为5个整数指数')
    if _conflict(db, data.study_id, data.code):
        raise HTTPException(409, '研究已定义该基础量')
    item = BaseMetric(study_id=data.study_id, code=data.code, name=data.name,
                      unit=data.unit, dims=list(data.dims), version=1)
    db.add(item)
    db.commit()
    return item


def update_base_metric(db, metric_id, data):
    item = db.get(BaseMetric, metric_id)
    if not item:
        raise HTTPException(404, '基础量不存在')
    if data.version is None:
        raise HTTPException(428, '缺少版本号，无法进行并发编辑校验')
    if item.version != data.version:
        raise HTTPException(409, '基础量已被他人修改，请刷新后基于最新版本编辑')
    if item.study_id != data.study_id or item.code != data.code:
        raise HTTPException(422, '不能修改基础量所属研究或代码（测量值按代码关联）')
    if not is_valid_dims(data.dims):
        raise HTTPException(422, '量纲须为5个整数指数')
    if list(item.dims) != list(data.dims):
        _check_study_consistency(db, item.study_id, item.code, data.dims)
    item.name, item.unit, item.dims = data.name, data.unit, list(data.dims)
    item.version += 1
    # A base criterion sharing the same code is the same physical quantity:
    # keep its dimensions in lock-step and bump its optimistic-lock version.
    criterion = db.scalar(select(Criterion).where(
        Criterion.study_id == item.study_id, Criterion.code == item.code))
    if criterion is not None and list(criterion.dims) != list(data.dims):
        criterion.dims = list(data.dims)
        criterion.version += 1
    db.commit()
    return item


def _check_study_consistency(db, study_id, changed_code, new_dims):
    """A base-dimension edit must keep every derived formula of the study valid."""
    criteria = db.scalars(select(Criterion).where(Criterion.study_id == study_id)).all()
    catalog = {m.code: tuple(m.dims) for m in db.scalars(
        select(BaseMetric).where(BaseMetric.study_id == study_id)).all()}
    for legacy_code, meta in LEGACY_BASE.items():
        catalog.setdefault(legacy_code, tuple(meta['dims']))
    catalog[changed_code] = tuple(new_dims)
    by_code = {c.code: c for c in criteria}
    dicts = [{'code': c.code, 'kind': c.kind, 'formula': c.formula or '', 'dims': list(c.dims)}
             for c in criteria]
    base_refs = set(catalog) - set(by_code)
    try:
        topological_order(dicts, base_refs)
    except GraphError as exc:
        raise HTTPException(422, f'量纲变更会破坏派生关系：{exc}')
    # New base dimensions take precedence over stale criterion dimensions.
    ref_dims = {**{c.code: tuple(c.dims) for c in criteria}, **catalog}
    for c in criteria:
        if c.kind != 'derived' or changed_code not in dependencies(parse(c.formula or '')):
            continue
        try:
            inferred = infer_dimensions(parse(c.formula or ''), ref_dims)
        except FormulaError as exc:
            raise HTTPException(422, f'量纲变更使指标 {c.code} 公式失效：{exc}')
        if list(inferred) != list(c.dims):
            raise HTTPException(
                422, f'量纲变更会使指标 {c.code} 的推导量纲变为 {list(inferred)}，与登记量纲不一致；请先调整该指标')
