"""Derived-value cache and study-wide derivation preview.

Cache entries persist per (criterion, sample) with the full step trace.  A
definition or base-value change invalidates only the affected downstream
chains; untouched rows keep their cached values and provenance.
"""
from datetime import datetime
from sqlalchemy import select, delete
from src.models import DerivedValue, Criterion, MaterialSample, BaseMetric
from src.services.derivation.graph import evaluate_study, topological_order
from src.services.derivation.formula import dependencies, parse

LEGACY_CODES = ('absorption', 'impact', 'carbon', 'price', 'thickness')


def _criterion_dicts(criteria) -> list[dict]:
    return [{'code': c.code, 'kind': c.kind, 'formula': c.formula or '', 'dims': list(c.dims)}
            for c in criteria]


def _base_catalog(db, study_id) -> dict:
    catalog = {m.code: tuple(m.dims) for m in db.scalars(
        select(BaseMetric).where(BaseMetric.study_id == study_id)).all()}
    catalog.setdefault('absorption', (0, 0, 0, 0, 0))
    catalog.setdefault('impact', (0, 1, 0, 0, 0))
    catalog.setdefault('carbon', (1, 1, 0, 0, 0))
    catalog.setdefault('price', (1, 0, 0, 0, 1))
    catalog.setdefault('thickness', (1, 0, 0, 0, 0))
    return catalog


def _base_refs(criteria) -> set[str]:
    refs = set()
    for c in criteria:
        if c.kind == 'derived':
            refs |= dependencies(parse(c.formula or ''))
    criterion_codes = {c.code for c in criteria}
    return {r for r in refs if r not in criterion_codes}


def _sample_base_values(sample, all_base_codes) -> dict:
    measured = {m.metric_code: m.value for m in sample.measurement_rows}
    out = {}
    for code in all_base_codes:
        out[code] = getattr(sample, code) if code in LEGACY_CODES else measured.get(code)
    return out


def _cache_map(db, criterion_ids) -> dict:
    if not criterion_ids:
        return {}
    rows = db.scalars(select(DerivedValue).where(DerivedValue.criterion_id.in_(criterion_ids))).all()
    return {(r.criterion_id, r.sample_id): r for r in rows}


def invalidate_for(db, study_id, criterion_codes: set[str], sample_ids=None):
    """Delete cached rows of the given derived criteria (optionally one sample)."""
    if not criterion_codes:
        return
    criteria = db.scalars(select(Criterion).where(
        Criterion.study_id == study_id, Criterion.code.in_(criterion_codes))).all()
    ids = [c.id for c in criteria]
    if not ids:
        return
    stmt = delete(DerivedValue).where(DerivedValue.criterion_id.in_(ids))
    if sample_ids is not None:
        stmt = stmt.where(DerivedValue.sample_id.in_(list(sample_ids)))
    db.execute(stmt)


def recompute_study(db, study_id, only_codes: set[str] | None = None, sample_ids=None):
    """Recompute derived values; when only_codes is given, touch just that
    downstream chain.  Reads base values live, evaluates in topological order,
    and writes one cache row per (derived criterion, sample)."""
    criteria = db.scalars(select(Criterion).where(Criterion.study_id == study_id)
                          .order_by(Criterion.code)).all()
    derived = [c for c in criteria if c.kind == 'derived']
    if not derived:
        return
    base_catalog = _base_catalog(db, study_id)
    base_refs = _base_refs(criteria)
    dicts = _criterion_dicts(criteria)
    order = topological_order(dicts, base_refs)
    derived_codes = {c.code for c in derived}
    # Base criteria have no cache rows; never create them.
    targets = (set(only_codes) if only_codes else derived_codes) & derived_codes
    sample_query = select(MaterialSample).order_by(MaterialSample.code)
    if sample_ids is not None:
        sample_query = sample_query.where(MaterialSample.id.in_(list(sample_ids)))
    samples = db.scalars(sample_query).all()
    cache = _cache_map(db, [c.id for c in derived])
    by_code = {c.code: c for c in criteria}
    criterion_base_codes = [c.code for c in criteria if c.kind == 'base']
    all_base_codes = set(criterion_base_codes) | base_refs
    for sample in samples:
        base_values = _sample_base_values(sample, all_base_codes)
        values, traces, _missing = evaluate_study(dicts, base_values, base_catalog)
        for code in order:
            if code not in targets:
                continue
            criterion = by_code[code]
            row = cache.get((criterion.id, sample.id))
            if row is None:
                row = DerivedValue(criterion_id=criterion.id, sample_id=sample.id)
                db.add(row)
                cache[(criterion.id, sample.id)] = row
            row.value = values.get(code)
            row.trace = traces.get(code, {})
            row.updated_at = datetime.utcnow()
    db.flush()


def preview_study(db, study_id):
    """Read-side preview: per sample derivation tree and exclusion reasons."""
    study_criteria = db.scalars(select(Criterion).where(Criterion.study_id == study_id)
                                .order_by(Criterion.code)).all()
    samples = db.scalars(select(MaterialSample).order_by(MaterialSample.code)).all()
    base_catalog = _base_catalog(db, study_id)
    base_refs = _base_refs(study_criteria)
    dicts = _criterion_dicts(study_criteria)
    criterion_base_codes = [c.code for c in study_criteria if c.kind == 'base']
    all_base_codes = set(criterion_base_codes) | base_refs
    preview = []
    for sample in samples:
        base_values = _sample_base_values(sample, all_base_codes)
        values, traces, missing = evaluate_study(dicts, base_values, base_catalog)
        exclusions = [{'code': code, 'reason': reason} for code, reason in sorted(missing.items())]
        preview.append({'sample_id': sample.id, 'code': sample.code, 'name': sample.name,
                        'values': {c.code: values.get(c.code) for c in study_criteria},
                        'traces': [traces[c.code] for c in study_criteria
                                   if c.kind == 'derived' and c.code in traces],
                        'exclusions': exclusions})
    return {'criteria': [{'code': c.code, 'name': c.name, 'unit': c.unit, 'kind': c.kind,
                          'formula': c.formula, 'dims': list(c.dims), 'version': c.version}
                         for c in study_criteria],
            'samples': preview,
            'excluded_sample_ids': sorted({p['sample_id'] for p in preview if p['exclusions']})}
