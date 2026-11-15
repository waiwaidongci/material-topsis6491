"""Sample measurements bridge the legacy five columns and the extensible table.

Legacy codes (absorption/impact/carbon/price/thickness) read and write the
fixed columns of material_samples so migrated trade-offs keep their values.
New research-defined base quantities live in sample_measurements and allow
explicit NULL (recorded-missing) for propagation.
"""
from sqlalchemy import select
from fastapi import HTTPException
from src.models import MaterialSample, SampleMeasurement, BaseMetric, Criterion
from src.services.base_metric_service import LEGACY_BASE
from src.services import derivation_service as derived

LEGACY_CODES = set(LEGACY_BASE)


def get_value(sample: MaterialSample, code: str):
    if code in LEGACY_CODES:
        return getattr(sample, code)
    return next((m.value for m in sample.measurement_rows if m.metric_code == code), None)


def base_values_for(db, sample: MaterialSample, metric_codes) -> dict:
    rows = {m.metric_code: m.value for m in db.scalars(
        select(SampleMeasurement).where(SampleMeasurement.sample_id == sample.id)).all()}
    out = {}
    for code in metric_codes:
        out[code] = getattr(sample, code) if code in LEGACY_CODES else rows.get(code)
    return out


def list_measurements(db, study_id):
    metrics = db.scalars(select(BaseMetric).where(BaseMetric.study_id == study_id)).all()
    codes = [m.code for m in metrics]
    samples = db.scalars(select(MaterialSample).order_by(MaterialSample.code)).all()
    rows = {(m.sample_id, m.metric_code): m.value
            for m in db.scalars(select(SampleMeasurement)).all()}
    return [{'sample_id': s.id, 'code': code,
             'value': getattr(s, code) if code in LEGACY_CODES else rows.get((s.id, code))}
            for s in samples for code in codes]


def upsert_measurement(db, sample_id, metric_code, value):
    sample = db.get(MaterialSample, sample_id)
    if not sample:
        raise HTTPException(404, '试样不存在')
    if metric_code in LEGACY_CODES:
        if value is None:
            raise HTTPException(422, '迁移保留的五项固定基础量不允许置空（旧权衡依赖）')
        setattr(sample, metric_code, value)
        db.commit()
        return
    metric = db.scalar(select(BaseMetric).where(BaseMetric.code == metric_code))
    if not metric:
        raise HTTPException(422, f'基础量未定义: {metric_code}')
    row = db.scalar(select(SampleMeasurement).where(
        SampleMeasurement.sample_id == sample_id, SampleMeasurement.metric_code == metric_code))
    if row:
        row.value = value
    else:
        db.add(SampleMeasurement(sample_id=sample_id, metric_code=metric_code, value=value))
    db.commit()
    recompute_sample_derived(db, sample_id)
    db.commit()


def recompute_sample_derived(db, sample_id):
    """After a base value changes, refresh only this sample's downstream chain
    in every study that defines derived criteria."""
    study_ids = [sid for (sid,) in db.execute(select(Criterion.study_id).distinct()).all()]
    for study_id in study_ids:
        criteria = db.scalars(select(Criterion).where(Criterion.study_id == study_id)).all()
        codes = {c.code for c in criteria if c.kind == 'derived'}
        if not codes:
            continue
        derived.invalidate_for(db, study_id, codes, sample_ids=[sample_id])
        derived.recompute_study(db, study_id, only_codes=codes, sample_ids=[sample_id])
