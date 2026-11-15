"""End-to-end service behaviour: definitions, incremental recompute, freeze."""
import pytest
from fastapi import HTTPException
from src.models import CandidateStudy, MaterialSample, Criterion, BaseMetric, SampleMeasurement
from src.schemas.criterion import CriterionInput
from src.schemas.sample import SampleInput
from src.schemas.metric import BaseMetricInput
from src.services import criterion_service, sample_service, derivation_service
from src.services.freeze_service import build_freeze
from src.services.run_service import create_run
from src.services.weight_sensitivity import analyze_decision
from src.schemas.run import RunInput


def _study(db):
    s = CandidateStudy(code='S1', name='研究一', context='', source_file='x.csv', material_ids=[])
    db.add(s); db.flush()
    samples = []
    for i in range(4):
        m = MaterialSample(code=f'LY{i+1:02}', name=f'材料{i}', family='板',
                           absorption=0.6 + i * 0.05, impact=8.0, carbon=2.0,
                           price=100.0 + i, thickness=20.0 + i, batch='b')
        db.add(m); db.flush()
        samples.append(m)
    s.material_ids = [m.id for m in samples]
    db.commit()
    return s, samples


def _criterion(study_id, code, kind='base', formula='', dims=None, weight=1.0,
               direction='benefit', version=None):
    return CriterionInput(study_id=study_id, code=code, name=code, unit='u',
                          direction=direction, center_weight=weight, kind=kind,
                          formula=formula, dims=dims or [0] * 5, version=version)


def test_create_derived_criterion_and_cache(db):
    study, samples = _study(db)
    criterion_service.create_criterion(db, _criterion(study.id, 'absorption', dims=[0, 0, 0, 0, 0]))
    criterion_service.create_criterion(db, _criterion(study.id, 'thickness', dims=[1, 0, 0, 0, 0], direction='cost'))
    criterion_service.create_criterion(
        db, _criterion(study.id, 'absorption_per_mm', 'derived', 'absorption / thickness',
                       dims=[-1, 0, 0, 0, 0]))
    preview = derivation_service.preview_study(db, study.id)
    first = preview['samples'][0]
    assert first['values']['absorption_per_mm'] == pytest.approx(0.6 / 20.0)
    trace = next(t for t in first['traces'] if t['code'] == 'absorption_per_mm')
    assert trace['inputs'] == {'absorption': 0.6, 'thickness': 20.0}
    assert first['exclusions'] == []


def test_dimension_mismatch_rejected_at_definition(db):
    study, _ = _study(db)
    criterion_service.create_criterion(db, _criterion(study.id, 'absorption'))
    criterion_service.create_criterion(db, _criterion(study.id, 'thickness', dims=[1, 0, 0, 0, 0]))
    with pytest.raises(HTTPException) as exc:
        criterion_service.create_criterion(
            db, _criterion(study.id, 'bad', 'derived', 'absorption + thickness',
                           dims=[0, 0, 0, 0, 0]))
    assert exc.value.status_code == 422


def test_cycle_rejected(db):
    study, _ = _study(db)
    criterion_service.create_criterion(db, _criterion(study.id, 'aa'))
    criterion_service.create_criterion(db, _criterion(study.id, 'dd1', 'derived', 'aa + 1'))
    # dd2 -> dd1 would be fine; make dd1 -> dd2 by editing dd1 after dd2 exists -> cycle
    criterion_service.create_criterion(db, _criterion(study.id, 'dd2', 'derived', 'dd1'))
    dd1 = db.query(Criterion).filter_by(code='dd1').one()
    with pytest.raises(HTTPException) as exc:
        criterion_service.update_criterion(
            db, dd1.id, _criterion(study.id, 'dd1', 'derived', 'dd2', version=1))
    assert exc.value.status_code == 422


def test_optimistic_lock_concurrent_edit(db):
    study, _ = _study(db)
    item = criterion_service.create_criterion(db, _criterion(study.id, 'absorption'))
    # Stale version must be rejected with 409.
    with pytest.raises(HTTPException) as exc:
        criterion_service.update_criterion(
            db, item.id, _criterion(study.id, 'absorption', weight=2.0, version=item.version - 1))
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        criterion_service.update_criterion(
            db, item.id, _criterion(study.id, 'absorption', weight=2.0))
    assert exc.value.status_code == 428


def test_incremental_recompute_only_affected_chain(db):
    study, samples = _study(db)
    criterion_service.create_criterion(db, _criterion(study.id, 'absorption'))
    criterion_service.create_criterion(db, _criterion(study.id, 'thickness', dims=[1, 0, 0, 0, 0]))
    criterion_service.create_criterion(
        db, _criterion(study.id, 'per_mm', 'derived', 'absorption / thickness', dims=[-1, 0, 0, 0, 0]))
    criterion_service.create_criterion(db, _criterion(study.id, 'standalone', 'derived', 'absorption'))
    from src.models import DerivedValue
    from sqlalchemy import select
    standalone = db.query(Criterion).filter_by(code='standalone').one()
    per_mm = db.query(Criterion).filter_by(code='per_mm').one()
    standalone_row_id = db.scalar(select(DerivedValue.id).where(
        DerivedValue.criterion_id == standalone.id, DerivedValue.sample_id == samples[0].id))
    per_mm_row_id = db.scalar(select(DerivedValue.id).where(
        DerivedValue.criterion_id == per_mm.id, DerivedValue.sample_id == samples[0].id))
    # Editing thickness recomputes per_mm (row deleted and recreated) but leaves
    # the unrelated standalone cache row exactly in place.
    thickness = db.query(Criterion).filter_by(code='thickness').one()
    criterion_service.update_criterion(
        db, thickness.id,
        _criterion(study.id, 'thickness', dims=[1, 0, 0, 0, 0], direction='cost',
                   version=thickness.version))
    db.expire_all()
    assert db.scalar(select(DerivedValue.id).where(
        DerivedValue.criterion_id == standalone.id,
        DerivedValue.sample_id == samples[0].id)) == standalone_row_id
    new_per_mm_id = db.scalar(select(DerivedValue.id).where(
        DerivedValue.criterion_id == per_mm.id, DerivedValue.sample_id == samples[0].id))
    assert new_per_mm_id != per_mm_row_id
    refreshed = db.get(DerivedValue, new_per_mm_id)
    assert refreshed.value == pytest.approx(0.6 / 20.0)


def test_missing_measurement_excludes_freeze_and_preview_shows_reason(db):
    study, samples = _study(db)
    # Custom base metric areal_density with one missing sample.
    from src.services.base_metric_service import create_base_metric
    create_base_metric(db, BaseMetricInput(
        study_id=study.id, code='areal_density', name='面密度', unit='kg/m²', dims=[-2, 1, 0, 0, 0]))
    for m in samples:
        db.add(SampleMeasurement(sample_id=m.id, metric_code='areal_density',
                                 value=None if m.id == samples[0].id else 3.0))
    db.commit()
    criterion_service.create_criterion(db, _criterion(study.id, 'absorption'))
    criterion_service.create_criterion(
        db, _criterion(study.id, 'areal_density', dims=[-2, 1, 0, 0, 0], direction='cost'))
    criterion_service.create_criterion(
        db, _criterion(study.id, 'mass_cost', 'derived', 'absorption / areal_density',
                       dims=[2, -1, 0, 0, 0], direction='cost'))
    preview = derivation_service.preview_study(db, study.id)
    excluded = next(p for p in preview['samples'] if p['sample_id'] == samples[0].id)
    assert any(r['code'] == 'mass_cost' for r in excluded['exclusions'])
    # Freeze must refuse and publish nothing.
    before = len(db.query(__import__('src.models', fromlist=['DecisionRun']).DecisionRun).all())
    with pytest.raises(HTTPException) as exc:
        build_freeze(db, study)
    assert exc.value.status_code == 422
    assert len(db.query(__import__('src.models', fromlist=['DecisionRun']).DecisionRun).all()) == before


def test_freeze_snapshot_carries_provenance_and_run_recomputes(db):
    study, samples = _study(db)
    criterion_service.create_criterion(db, _criterion(study.id, 'absorption'))
    criterion_service.create_criterion(db, _criterion(study.id, 'thickness', dims=[1, 0, 0, 0, 0], direction='cost'))
    criterion_service.create_criterion(
        db, _criterion(study.id, 'per_mm', 'derived', 'absorption / thickness', dims=[-1, 0, 0, 0, 0]))
    snapshot, weights, version_hash = build_freeze(db, study)
    assert snapshot['schema_version'] == 'derived-v2'
    assert snapshot['definition_version'] == version_hash
    assert snapshot['provenance'][samples[0].code]['per_mm']['inputs']
    frozen_value = snapshot['samples'][0]['per_mm']
    # Later edits must not change the frozen snapshot's values/provenance.
    thickness = db.query(Criterion).filter_by(code='thickness').one()
    criterion_service.update_criterion(
        db, thickness.id,
        _criterion(study.id, 'thickness', dims=[1, 0, 0, 0, 0], direction='cost',
                   version=thickness.version))
    run = create_run(db, RunInput(name='run-1', study_id=study.id))
    # The new run carries its own complete definition version and snapshot.
    assert run.definition_version and run.definition_version != version_hash
    assert run.snapshot['definition_version'] == run.definition_version
    result = analyze_decision(run.snapshot, run.center_weights, 40, 1000, 20261112)
    assert len(result['samples']) == 4
    assert len(result['fingerprint']) == 64
    # Both runs derive the same per_mm because the thickness edit kept the value;
    # what matters is each snapshot is internally complete and self-consistent.
    assert run.snapshot['samples'][0]['per_mm'] == pytest.approx(frozen_value)
    assert result['samples'][0]['per_mm'] == pytest.approx(frozen_value)
