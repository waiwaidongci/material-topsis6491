"""Build the complete frozen version for a trade-off run.

The freeze happens inside one transaction and captures, together:
  * every candidate's base values,
  * every derived value and its step-by-step provenance trace,
  * the criterion definitions (formula, dimensions, version),
  * the explicit list of excluded candidates with reasons.

A run is only queued when every candidate has a finite non-negative value for
every active criterion.  Otherwise the transaction raises and no half-computed
row is published; the preview endpoint explains the same exclusion reasons
beforehand.
"""
import hashlib
import json
from sqlalchemy import select
from fastapi import HTTPException
from src.models import DecisionRun, MaterialSample, Criterion, BaseMetric
from src.services.derivation.graph import evaluate_study, topological_order
from src.services.derivation.formula import dependencies, parse
from src.services.derivation_service import _criterion_dicts

LEGACY_CODES = ('absorption', 'impact', 'carbon', 'price', 'thickness')


def _base_catalog(db, study_id):
    catalog = {m.code: tuple(m.dims) for m in db.scalars(
        select(BaseMetric).where(BaseMetric.study_id == study_id)).all()}
    catalog.setdefault('absorption', (0, 0, 0, 0, 0))
    catalog.setdefault('impact', (0, 1, 0, 0, 0))
    catalog.setdefault('carbon', (1, 1, 0, 0, 0))
    catalog.setdefault('price', (1, 0, 0, 0, 1))
    catalog.setdefault('thickness', (1, 0, 0, 0, 0))
    return catalog


def _base_values(sample, base_codes, measured):
    out = {}
    for code in base_codes:
        out[code] = getattr(sample, code) if code in LEGACY_CODES else measured.get(code)
    return out


def build_freeze(db, study, weights_override=None):
    criteria = db.scalars(select(Criterion).where(
        Criterion.study_id == study.id).order_by(Criterion.code)).all()
    if not 1 <= len(criteria) <= 5:
        raise HTTPException(422, '研究需要1–5个指标才能冻结权衡')
    codes = [c.code for c in criteria]
    weights = weights_override or {c.code: c.center_weight for c in criteria}
    if set(weights) != set(codes):
        raise HTTPException(422, '中心权重须逐一覆盖本研究指标')
    samples = db.scalars(select(MaterialSample).where(
        MaterialSample.id.in_(study.material_ids)).order_by(MaterialSample.code)).all()
    if not 2 <= len(samples) <= 120:
        raise HTTPException(422, '候选试样须为2–120份')
    dicts = _criterion_dicts(criteria)
    base_catalog = _base_catalog(db, study.id)
    base_refs = set()
    for c in criteria:
        if c.kind == 'derived':
            base_refs |= dependencies(parse(c.formula or ''))
    base_refs = {r for r in base_refs if r not in {c.code for c in criteria}}
    order = topological_order(dicts, base_refs)
    base_codes = [c.code for c in criteria if c.kind == 'base']
    all_base_codes = set(base_codes) | base_refs
    frozen_samples, exclusions, traces_all = [], [], {}
    for sample in samples:
        measured = {m.metric_code: m.value for m in sample.measurement_rows}
        base_values = _base_values(sample, all_base_codes, measured)
        values, traces, missing = evaluate_study(dicts, base_values, base_catalog)
        row = {'id': sample.id, 'code': sample.code, 'name': sample.name,
               'family': sample.family, 'batch': sample.batch}
        row.update({code: values.get(code) for code in codes})
        if missing:
            exclusions.append({'sample_id': sample.id, 'code': sample.code,
                               'name': sample.name, 'reasons': missing})
            traces_all[sample.code] = traces
            continue
        frozen_samples.append(row)
        traces_all[sample.code] = traces
    if exclusions:
        raise HTTPException(
            422,
            {'message': '存在缺测或无法计算的候选，冻结已取消（未发布半算结果）',
             'exclusions': exclusions,
             'hint': '请先在“试样与口径 · 派生预览”核对排除原因，补齐基础量或调整候选集合'})
    if len(frozen_samples) < 2:
        raise HTTPException(422, '排除缺测后有效候选不足2份，无法建立权衡')
    base_metrics = [{'code': m.code, 'name': m.name, 'unit': m.unit,
                     'dims': list(m.dims), 'version': m.version}
                    for m in db.scalars(select(BaseMetric).where(BaseMetric.study_id == study.id)).all()]
    criterion_snapshot = [{'id': c.id, 'code': c.code, 'name': c.name, 'unit': c.unit,
                           'direction': c.direction, 'center_weight': c.center_weight,
                           'kind': c.kind, 'formula': c.formula, 'dims': list(c.dims),
                           'version': c.version} for c in criteria]
    definition = {'criteria': criterion_snapshot, 'base_metrics': base_metrics,
                  'topological_order': order}
    version_hash = hashlib.sha256(json.dumps(
        definition, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    snapshot = {
        'schema_version': 'derived-v2',
        'definition_version': version_hash,
        'study': {'id': study.id, 'code': study.code, 'name': study.name,
                  'source_file': study.source_file, 'material_ids': study.material_ids},
        'base_metrics': base_metrics,
        'criteria': criterion_snapshot,
        'topological_order': order,
        'samples': frozen_samples,
        # provenance[sample_code][criterion_code] = trace with inputs and reason
        'provenance': traces_all,
        'excluded': exclusions,
    }
    return snapshot, weights, version_hash
