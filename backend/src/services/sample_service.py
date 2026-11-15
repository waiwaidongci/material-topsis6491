from sqlalchemy import select,func
from fastapi import HTTPException
from src.models import MaterialSample,SampleMeasurement,BaseMetric
from src.services.measurement_service import recompute_sample_derived

LEGACY_CODES=('absorption','impact','carbon','price','thickness')

def list_samples(db):
    return db.scalars(select(MaterialSample).order_by(MaterialSample.code)).all()

def validate(db,data,id=None):
    if db.scalar(select(MaterialSample).where(MaterialSample.code==data.code,MaterialSample.id!=(id or 0))):
        raise HTTPException(409,'试样编号已存在')

def _measurement_codes(db):
    return {m.code for m in db.scalars(select(BaseMetric)).all()}

def create_sample(db,data):
    validate(db,data)
    if db.scalar(select(func.count()).select_from(MaterialSample))>=300:
        raise HTTPException(422,'资料库最多300份试样')
    payload=data.model_dump(exclude={'measurements'})
    item=MaterialSample(**payload);db.add(item);db.flush()
    _write_measurements(db,item,data.measurements)
    db.commit()
    recompute_sample_derived(db,item.id)
    db.commit()
    return item

def update_sample(db,id,data):
    item=db.get(MaterialSample,id)
    if not item:raise HTTPException(404,'试样不存在')
    validate(db,data,id)
    for code in LEGACY_CODES:
        setattr(item,code,getattr(data,code))
    item.name,item.family,item.batch=data.name,data.family,data.batch
    _write_measurements(db,item,data.measurements)
    db.commit()
    recompute_sample_derived(db,item.id)
    db.commit()
    return item

def _write_measurements(db,sample,measurements:dict):
    known=_measurement_codes(db)-set(LEGACY_CODES)
    for code,value in measurements.items():
        if code in LEGACY_CODES:
            raise HTTPException(422,f'{code} 是固定基础量，请使用专用列字段')
        if code not in known:
            raise HTTPException(422,f'基础量未定义: {code}')
        if value is not None and (value!=value or value in (float('inf'),float('-inf')) or value<0):
            raise HTTPException(422,f'{code} 须为有限非负数，或显式置空表达缺测')
        row=db.scalar(select(SampleMeasurement).where(
            SampleMeasurement.sample_id==sample.id,SampleMeasurement.metric_code==code))
        if row:row.value=value
        else:db.add(SampleMeasurement(sample_id=sample.id,metric_code=code,value=value))
