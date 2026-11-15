"""HTTP-level integration: auth, validation, conflicts, freeze refusal."""
import os
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('SEED_DEMO', 'false')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.mysql import DOUBLE as MySQLDouble
from fastapi.testclient import TestClient

MySQLDouble.__visit_name__ = 'FLOAT'
from src.config import database as db_module
from src.config.database import Base
import src.models  # noqa
from scripts.seed_demo import seed


@pytest.fixture(scope='module')
def client():
    eng = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False},
                        poolclass=StaticPool)
    db_module.engine = eng
    from sqlalchemy.orm import sessionmaker
    db_module.Session.configure(bind=eng)
    Base.metadata.create_all(eng)
    seed()

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def incr(self, key):
            self.store[key] = self.store.get(key, 0) + 1
            return self.store[key]

        def expire(self, key, seconds):
            return True

        def ping(self):
            return True

    fake = FakeRedis()
    import src.middlewares.rate_limit as rl
    rl.Redis.from_url = staticmethod(lambda url: fake)
    import src.main as main_mod
    main_mod.Redis.from_url = staticmethod(lambda url: fake)

    from src.main import app
    with TestClient(app) as c:
        yield c


def _token(client, role):
    resp = client.post('/auth/login', json={'email': f'{role}@luyan.local', 'password': 'Luyan2026!'})
    assert resp.status_code == 200, resp.text
    return resp.json()['token']


def _auth(role):
    return lambda client=lambda: None: None


def test_viewer_cannot_write(client):
    token = _token(client, 'viewer')
    r = client.post('/metrics', json={'study_id': 1, 'code': 'new_metric', 'name': '新量',
                                      'unit': 'x', 'dims': [0, 0, 0, 0, 0]},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_base_metric_lifecycle_and_dim_validation(client):
    token = _token(client, 'analyst')
    h = {'Authorization': f'Bearer {token}'}
    r = client.post('/metrics', json={'study_id': 1, 'code': 'test_areal_x', 'name': '面密度',
                                      'unit': 'kg/m2', 'dims': [-2, 1, 0, 0, 0]}, headers=h)
    assert r.status_code == 201, r.text
    metric_id = r.json()['id']
    # Bad dimensions (4 entries) rejected.
    r = client.put(f'/metrics/{metric_id}', json={'study_id': 1, 'code': 'test_areal_x',
                   'name': '面密度', 'unit': 'kg/m2', 'dims': [0, 0, 0, 0], 'version': 1}, headers=h)
    assert r.status_code == 422
    # Stale version conflict.
    r = client.put(f'/metrics/{metric_id}', json={'study_id': 1, 'code': 'test_areal_x',
                   'name': '面密度改', 'unit': 'kg/m2', 'dims': [-2, 1, 0, 0, 0], 'version': 99}, headers=h)
    assert r.status_code == 409


def test_criterion_formula_dimension_and_cycle(client):
    token = _token(client, 'analyst')
    h = {'Authorization': f'Bearer {token}'}
    studies = client.get('/studies', headers=h).json()
    # Use a legacy study (5 base criteria, no derived) — but it is also full, so
    # create a dedicated study to exercise formula validation below the cap.
    new_study = client.post('/studies', json={'code': 'LY-TEST-FORMULA', 'name': '公式校验研究',
                            'context': '', 'source_file': 't.csv',
                            'material_ids': studies[0]['material_ids'][:4]}, headers=h)
    assert new_study.status_code == 201, new_study.text
    sid = new_study.json()['id']
    base = [('absorption', '吸声', 'αw', 'benefit', [0, 0, 0, 0, 0]),
            ('thickness', '厚度', 'mm', 'cost', [1, 0, 0, 0, 0])]
    for code, name, unit, direction, dims in base:
        r = client.post('/criteria', json={'study_id': sid, 'code': code, 'name': name,
                        'unit': unit, 'direction': direction, 'center_weight': 1.0,
                        'kind': 'base', 'dims': dims}, headers=h)
        assert r.status_code == 201, r.text
    # Dimensionally inconsistent formula: absorption (dimensionless) + thickness (L).
    r = client.post('/criteria', json={'study_id': sid, 'code': 'bad_dims', 'name': '错量纲',
                    'unit': 'x', 'direction': 'benefit', 'center_weight': 1.0,
                    'kind': 'derived', 'formula': 'absorption + thickness',
                    'dims': [0, 0, 0, 0, 0]}, headers=h)
    assert r.status_code == 422 and '量纲' in r.json()['detail']
    # Unknown reference rejected.
    r = client.post('/criteria', json={'study_id': sid, 'code': 'ghost_ref', 'name': '幽灵引用',
                    'unit': 'x', 'direction': 'benefit', 'center_weight': 1.0,
                    'kind': 'derived', 'formula': 'ghost_x + 1', 'dims': [0, 0, 0, 0, 0]}, headers=h)
    assert r.status_code == 422
    # A consistent derived criterion is accepted, then a self-cycle via edit is rejected.
    r = client.post('/criteria', json={'study_id': sid, 'code': 'per_mm', 'name': '单位厚度吸声',
                    'unit': 'x', 'direction': 'benefit', 'center_weight': 1.0,
                    'kind': 'derived', 'formula': 'absorption / thickness',
                    'dims': [-1, 0, 0, 0, 0]}, headers=h)
    assert r.status_code == 201, r.text
    cid = r.json()['id']
    r = client.put(f'/criteria/{cid}', json={'study_id': sid, 'code': 'per_mm', 'name': '单位厚度吸声',
                   'unit': 'x', 'direction': 'benefit', 'center_weight': 1.0,
                   'kind': 'derived', 'formula': 'per_mm + 1', 'dims': [-1, 0, 0, 0, 0],
                   'version': 1}, headers=h)
    assert r.status_code == 422


def test_preview_excludes_missing_sample(client):
    token = _token(client, 'viewer')
    h = {'Authorization': f'Bearer {token}'}
    studies = client.get('/studies', headers=h).json()
    sid = next(s['id'] for s in studies if s['code'] == 'LY-DERIVED')
    preview = client.get(f'/metrics/preview?study_id={sid}', headers=h).json()
    excluded = [p for p in preview['samples'] if p['exclusions']]
    assert any(p['code'] == 'LY12' for p in excluded)
    ly12 = next(p for p in excluded if p['code'] == 'LY12')
    assert any(x['code'] == 'mass_cost' for x in ly12['exclusions'])


def test_freeze_refuses_when_missing_candidate_included(client):
    token = _token(client, 'analyst')
    h = {'Authorization': f'Bearer {token}'}
    studies = client.get('/studies', headers=h).json()
    study = next(s for s in studies if s['code'] == 'LY-DERIVED')
    sample_code_to_id = {s['code']: s['id'] for s in client.get('/samples', headers=h).json()}
    # Temporarily include the missing-measurement sample.
    ids = set(study['material_ids']) | {sample_code_to_id['LY12']}
    r = client.put(f"/studies/{study['id']}", json={**study, 'material_ids': sorted(ids)}, headers=h)
    assert r.status_code == 200, r.text
    before = len(client.get('/runs', headers=h).json())
    r = client.post('/runs', json={'name': 'should-not-exist', 'study_id': study['id'],
                                   'concentration': 40, 'repeats': 1000, 'seed': 1}, headers=h)
    assert r.status_code == 422
    detail = r.json()['detail']
    assert isinstance(detail, dict) and 'exclusions' in detail
    assert len(client.get('/runs', headers=h).json()) == before  # no half-computed run
    # Restore candidate set.
    r = client.put(f"/studies/{study['id']}", json={**study,
                   'material_ids': [i for i in sorted(ids) if i != sample_code_to_id['LY12']]}, headers=h)
    assert r.status_code == 200
