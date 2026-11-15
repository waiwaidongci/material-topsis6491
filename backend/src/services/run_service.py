import json
from pathlib import Path
from sqlalchemy import select,func
from sqlalchemy.orm import defer
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import DecisionRun
from src.services.study_service import get_study
from src.services.weight_sensitivity import analyze_decision
from src.services.freeze_service import build_freeze
redis=Redis.from_url(REDIS_URL)
def list_runs(db):return db.scalars(select(DecisionRun).options(defer(DecisionRun.result),defer(DecisionRun.snapshot)).order_by(DecisionRun.id.desc())).all()
def get_run(db,id):
    item=db.get(DecisionRun,id)
    if not item:raise HTTPException(404,'权衡任务不存在')
    return item

def create_run(db,data):
    study=get_study(db,data.study_id)
    if db.scalar(select(DecisionRun).where(DecisionRun.name==data.name)):raise HTTPException(409,'任务名称已存在')
    if db.scalar(select(func.count()).select_from(DecisionRun).where(DecisionRun.status.in_(['queued','running'])))>=3:raise HTTPException(429,'已有3项活动任务，请等待完成')
    # Single-transaction freeze: raise before any row is inserted when a
    # candidate cannot be fully derived, so no half-computed run is published.
    snapshot,weights,version_hash=build_freeze(db,study,data.center_weights or None)
    item=DecisionRun(name=data.name,study_id=study.id,center_weights=weights,
                     concentration=data.concentration,repeats=data.repeats,seed=data.seed,
                     snapshot=snapshot,definition_version=version_hash,
                     summary={'samples':len(snapshot['samples']),'criteria':len(snapshot['criteria']),
                              'definition_version':version_hash},
                     status='queued')
    db.add(item);db.commit()
    try:redis.lpush('material:runs',str(item.id))
    except Exception:pass
    return item

def execute_run(db,id):
    item=get_run(db,id)
    if item.status not in ('queued','running'):return
    item.status='running';db.commit()
    try:
        # The worker recomputes purely from the frozen snapshot; later edits to
        # definitions or base values never alter an already queued trade-off.
        result=analyze_decision(item.snapshot,item.center_weights,item.concentration,item.repeats,item.seed,lambda:Path('/tmp/heartbeat').touch())
        Path('/artifacts').mkdir(exist_ok=True);Path(f'/artifacts/run-{id}.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
        item.result=result;item.summary={'samples':len(result['samples']),'criteria':len(result['criteria']),'all_indistinguishable':result['all_indistinguishable'],'fingerprint':result['fingerprint'],'definition_version':item.definition_version};item.error='';item.status='completed';db.commit()
    except Exception as exc:
        db.rollback();item=get_run(db,id);item.status='failed';item.error=str(exc)[:600];db.commit()
