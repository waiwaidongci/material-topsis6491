import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
os.environ['JWT_SECRET'] = 'x'
os.environ['SEED_DEMO'] = 'false'

from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import DOUBLE as MySQLDouble
MySQLDouble.__visit_name__ = 'FLOAT'

from src.config import database as db_module
eng = create_engine('sqlite:///:memory:')
db_module.engine = eng
db_module.Session.configure(bind=eng)
import src.models  # noqa
from src.config.database import Base
Base.metadata.create_all(eng)

from scripts.seed_demo import seed
seed()

from sqlalchemy import select
from src.config.database import Session
from src.models import CandidateStudy, Criterion, MaterialSample, SampleMeasurement
from src.services import derivation_service, criterion_service
from src.services.freeze_service import build_freeze
from src.services.run_service import create_run
from src.services.weight_sensitivity import analyze_decision
from src.schemas.run import RunInput
from fastapi import HTTPException

with Session() as db:
    studies = db.scalars(select(CandidateStudy).order_by(CandidateStudy.id)).all()
    print('studies:', [(s.code, len(s.material_ids)) for s in studies])
    derived_study = next(s for s in studies if s.code == 'LY-DERIVED')
    crits = db.scalars(select(Criterion).where(Criterion.study_id == derived_study.id)).all()
    print('derived criteria:', [(c.code, c.kind, c.formula, c.dims, c.version) for c in crits])

    preview = derivation_service.preview_study(db, derived_study.id)
    print('preview criteria:', [c['code'] for c in preview['criteria']])
    print('excluded sample ids:', preview['excluded_sample_ids'])
    miss = next(p for p in preview['samples'] if p['exclusions'])
    print('exclusion example:', miss['code'], miss['exclusions'])
    ok = next(p for p in preview['samples'] if not p['exclusions'])
    tr = next(t for t in ok['traces'] if t['code'] == 'mass_cost')
    print('trace mass_cost:', tr)

    # Freeze the derived study (missing sample excluded from candidate set).
    snap, weights, vh = build_freeze(db, derived_study)
    print('freeze ok:', snap['schema_version'], len(snap['samples']), vh[:12])
    run = create_run(db, RunInput(name='smoke-derived', study_id=derived_study.id))
    result = analyze_decision(run.snapshot, run.center_weights, 40, 1000, 20261112)
    print('analyze ok:', len(result['samples']), 'samples; fp len', len(result['fingerprint']))
    print('rank row keys sample:', sorted(k for k in result['samples'][0] if k in
          ('absorption', 'thickness', 'areal_density', 'absorption_per_mm', 'mass_cost')))

    # Legacy study still freezes and computes exactly as before (v1-style).
    bal = next(s for s in studies if s.code == 'LY-BAL')
    run2 = create_run(db, RunInput(name='smoke-legacy', study_id=bal.id))
    r2 = analyze_decision(run2.snapshot, run2.center_weights, 40, 1000, 20261112)
    print('legacy analyze ok:', len(r2['samples']), r2['criteria'][0]['code'])

    # Freeze refusal: put the missing-measurement sample into the derived study.
    missing_sample = db.scalar(select(MaterialSample).where(MaterialSample.code == 'LY12'))
    derived_study.material_ids = sorted(set(derived_study.material_ids + [missing_sample.id]))
    db.commit()
    try:
        build_freeze(db, derived_study)
        print('ERROR: freeze should have refused')
    except HTTPException as exc:
        detail = exc.detail
        print('freeze refused:', exc.status_code, detail['message'])
        print('  exclusion codes:', [e['code'] for e in detail['exclusions']])

    # Old-shaped snapshot (v1, legacy five columns only) still analyzes.
    old_snapshot = run2.snapshot
    old_snapshot.pop('schema_version', None)
    r3 = analyze_decision(old_snapshot, run2.center_weights, 40, 1000, 20261112)
    print('v1-shaped snapshot recompute ok:', len(r3['samples']))

    # Optimistic lock conflict.
    c0 = crits[0]
    from src.schemas.criterion import CriterionInput
    stale = CriterionInput(study_id=c0.study_id, code=c0.code, name=c0.name, unit=c0.unit,
                           direction=c0.direction, center_weight=c0.center_weight,
                           kind=c0.kind, formula=c0.formula, dims=c0.dims, version=999)
    try:
        criterion_service.update_criterion(db, c0.id, stale)
        print('ERROR: stale version should conflict')
    except HTTPException as exc:
        print('optimistic lock:', exc.status_code, exc.detail)
print('SMOKE OK')
