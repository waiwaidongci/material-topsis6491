"""Base-metric dimension edits and measurement-driven recomputation."""
import pytest
from fastapi import HTTPException
from src.models import CandidateStudy, MaterialSample, Criterion, BaseMetric
from src.schemas.criterion import CriterionInput
from src.schemas.metric import BaseMetricInput
from src.services import criterion_service, base_metric_service, derivation_service
from sqlalchemy import select
from src.models import DerivedValue


def _setup(db):
    s = CandidateStudy(code='S2', name='研究二', context='', source_file='x.csv', material_ids=[])
    db.add(s); db.flush()
    samples = []
    for i in range(3):
        m = MaterialSample(code=f'M{i+1:02}', name=f'材料{i}', family='板',
                           absorption=0.7, impact=8.0, carbon=2.0, price=100.0,
                           thickness=20.0, batch='b')
        db.add(m); db.flush()
        samples.append(m)
    s.material_ids = [m.id for m in samples]
    base_metric_service.create_base_metric(db, BaseMetricInput(
        study_id=s.id, code='areal_density', name='面密度', unit='kg/m2', dims=[-2, 1, 0, 0, 0]))
    for m in samples:
        from src.models import SampleMeasurement
        db.add(SampleMeasurement(sample_id=m.id, metric_code='areal_density', value=3.0 + m.id))
    db.commit()
    criterion_service.create_criterion(db, CriterionInput(
        study_id=s.id, code='price', name='单价', unit='元/m2', direction='cost',
        center_weight=1.0, kind='base', dims=[1, 0, 0, 0, 1]))
    criterion_service.create_criterion(db, CriterionInput(
        study_id=s.id, code='areal_density', name='面密度', unit='kg/m2', direction='cost',
        center_weight=1.0, kind='base', dims=[-2, 1, 0, 0, 0]))
    derived = criterion_service.create_criterion(db, CriterionInput(
        study_id=s.id, code='mass_cost', name='单位质量价格', unit='元/kg', direction='cost',
        center_weight=1.0, kind='derived', formula='price / areal_density',
        dims=[3, -1, 0, 0, 1]))
    db.commit()
    return s, samples, derived


def test_base_dimension_edit_that_breaks_formula_is_rejected(db):
    study, samples, derived = _setup(db)
    metric = db.scalar(select(BaseMetric).where(
        BaseMetric.study_id == study.id, BaseMetric.code == 'areal_density'))
    # Changing areal_density from L^-2 M^1 to dimensionless makes
    # price / areal_density dimension L^1 ¥^1, no longer matching declared dims.
    bad = BaseMetricInput(study_id=study.id, code='areal_density', name='面密度',
                          unit='x', dims=[0, 0, 0, 0, 0], version=metric.version)
    with pytest.raises(HTTPException) as exc:
        base_metric_service.update_base_metric(db, metric.id, bad)
    assert exc.value.status_code == 422
    db.refresh(metric)
    assert metric.dims == [-2, 1, 0, 0, 0]  # unchanged after failed edit


def test_base_dimension_edit_consistent_keeps_formula(db):
    study, samples, derived = _setup(db)
    metric = db.scalar(select(BaseMetric).where(
        BaseMetric.study_id == study.id, BaseMetric.code == 'areal_density'))
    # A pure unit/name edit with identical dims is accepted.
    old_version = metric.version
    ok = BaseMetricInput(study_id=study.id, code='areal_density', name='面密度（复核）',
                         unit='kg·m^-2', dims=[-2, 1, 0, 0, 0], version=old_version)
    updated = base_metric_service.update_base_metric(db, metric.id, ok)
    assert updated.version == old_version + 1


def test_measurement_change_recomputes_only_that_sample(db):
    study, samples, derived = _setup(db)
    before = db.scalar(select(DerivedValue).where(
        DerivedValue.criterion_id == derived.id,
        DerivedValue.sample_id == samples[0].id))
    other_before = db.scalar(select(DerivedValue).where(
        DerivedValue.criterion_id == derived.id,
        DerivedValue.sample_id == samples[1].id))
    from src.services.measurement_service import upsert_measurement
    upsert_measurement(db, samples[0].id, 'areal_density', 9.9)
    db.expire_all()
    after = db.scalar(select(DerivedValue).where(
        DerivedValue.criterion_id == derived.id,
        DerivedValue.sample_id == samples[0].id))
    other_after = db.scalar(select(DerivedValue).where(
        DerivedValue.criterion_id == derived.id,
        DerivedValue.sample_id == samples[1].id))
    assert after.value == pytest.approx(100.0 / 9.9)
    # The untouched sample keeps its original cached value.
    assert other_after.value == other_before.value


def test_missing_measurement_makes_derived_none_with_trace(db):
    study, samples, derived = _setup(db)
    from src.services.measurement_service import upsert_measurement
    upsert_measurement(db, samples[0].id, 'areal_density', None)
    db.expire_all()
    row = db.scalar(select(DerivedValue).where(
        DerivedValue.criterion_id == derived.id,
        DerivedValue.sample_id == samples[0].id))
    assert row.value is None
    assert row.trace['excluded'] is True
    assert 'areal_density' in row.trace['reason']
    preview = derivation_service.preview_study(db, study.id)
    p = next(x for x in preview['samples'] if x['sample_id'] == samples[0].id)
    assert any(e['code'] == 'mass_cost' for e in p['exclusions'])
