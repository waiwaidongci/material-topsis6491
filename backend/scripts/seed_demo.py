"""Insert-only natural keys; global materials serve candidate studies.

Legacy three studies keep their five fixed base columns untouched, so existing
trade-offs and trial plans remain reproducible.  A new research-defined base
quantity (areal density) and a fourth study with derived criteria demonstrate
the derivation chain; one sample has an explicitly missing areal density to
show missing-value propagation and exclusion in the preview.
"""
import numpy as np
from sqlalchemy import select
from src.config.database import Base,engine,Session
from src.models import User,CandidateStudy,MaterialSample,Criterion,BaseMetric,SampleMeasurement

LEGACY_DIMS={
    'absorption':[0,0,0,0,0],
    'impact':[0,1,0,0,0],
    'carbon':[1,1,0,0,0],
    'price':[1,0,0,0,1],
    'thickness':[1,0,0,0,0],
}

def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role,name in [('admin','余芦 · 试样负责人'),('analyst','林砚 · 产品研究员'),('viewer','季乔 · 研发观察员')]:
            email=role+'@luyan.local'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,name=name,role=role,password_hash=__import__('src.utils.security',fromlist=['hash_password']).hash_password('Luyan2026!')))
        rng=np.random.default_rng(20261112);ids=[]
        for i in range(36):
            family=['芦芯纤维板','麻纤复合毡','矿纤混合板'][i//12];code=f'LY{i+1:02}';g=i//12
            a=float(rng.uniform([.62,.45,.70][g],[.93,.78,.98][g]));impact=float(rng.uniform([4,8,5][g],[9,17,12][g]));carbon=float(rng.uniform([.8,1.4,2.1][g],[1.9,3.4,4.8][g]));price=float(rng.uniform([65,75,90][g],[135,160,180][g]));thickness=float(rng.uniform([18,14,22][g],[36,30,42][g]))
            item=db.scalar(select(MaterialSample).where(MaterialSample.code==code))
            if not item:item=MaterialSample(code=code,name=family+' · '+str(i%12+1).zfill(2),family=family,absorption=a,impact=impact,carbon=carbon,price=price,thickness=thickness,batch='LYM-20261112');db.add(item);db.flush()
            ids.append(item.id)
        metrics=[('absorption','吸声系数','αw','benefit'),('impact','耐冲击','kJ/m²','benefit'),('carbon','碳强度','kgCO₂e/m²','cost'),('price','单位面积价格','元/m²','cost'),('thickness','厚度','mm','cost')]
        for code,name,weights in [('LY-BAL','芦芯展厅 · 均衡权衡',[.3,.2,.2,.2,.1]),('LY-CARBON','低碳会议室 · 碳优先',[.2,.15,.4,.15,.1]),('LY-THIN','薄型走廊 · 厚度约束',[.3,.15,.15,.15,.25])]:
            study=db.scalar(select(CandidateStudy).where(CandidateStudy.code==code))
            if not study:study=CandidateStudy(code=code,name=name,context='机构试样的偏好权重权衡；需要独立试样验证，不直接决定采购。',source_file='LYM_20261112_试样汇总.csv',material_ids=ids);db.add(study);db.flush()
            for (key,title,unit,direction),weight in zip(metrics,weights):
                if not db.scalar(select(Criterion).where(Criterion.study_id==study.id,Criterion.code==key)):db.add(Criterion(study_id=study.id,code=key,name=title,unit=unit,direction=direction,center_weight=weight,kind='base',formula='',dims=LEGACY_DIMS[key],version=1))
        db.flush()
        _seed_derived_demo(db,ids)
        db.commit()

def _seed_derived_demo(db,ids):
    # Areal density: kg/m² (length^-2, mass^1). One sample is explicitly missing.
    rng=np.random.default_rng(20261113)
    studies=db.scalars(select(CandidateStudy)).all()
    for study in studies:
        if not db.scalar(select(BaseMetric).where(BaseMetric.study_id==study.id,BaseMetric.code=='areal_density')):
            db.add(BaseMetric(study_id=study.id,code='areal_density',name='面密度',unit='kg/m²',dims=[-2,1,0,0,0],version=1))
    db.flush()
    for i,sample_id in enumerate(ids):
        g=i//12
        value=None if sample_id==ids[11] else float(rng.uniform([2.4,1.1,3.2][g],[5.6,2.8,7.4][g]))
        if not db.scalar(select(SampleMeasurement).where(SampleMeasurement.sample_id==sample_id,SampleMeasurement.metric_code=='areal_density')):
            db.add(SampleMeasurement(sample_id=sample_id,metric_code='areal_density',value=value))
    db.flush()
    if db.scalar(select(CandidateStudy).where(CandidateStudy.code=='LY-DERIVED')):return
    # The missing-measurement sample stays out of the candidate set so the
    # freeze succeeds; the preview still shows its exclusion reason.
    candidate_ids=[sid for sid in ids if sid!=ids[11]]
    study=CandidateStudy(code='LY-DERIVED',name='面密度与单位厚度吸声 · 派生权衡',
        context='研究组自定义基础量与逐级派生指标：面密度、单位厚度吸声参与权衡；缺测沿派生链传播。',
        source_file='LYM_20261112_试样汇总.csv',material_ids=candidate_ids)
    db.add(study);db.flush()
    rows=[
        ('thickness','厚度','mm','cost',.15,'base','',[1,0,0,0,0]),
        ('areal_density','面密度','kg/m²','cost',.30,'base','',[-2,1,0,0,0]),
        ('price','单位面积价格','元/m²','cost',.20,'base','',[1,0,0,0,1]),
        ('absorption_per_mm','单位厚度吸声','αw/mm','benefit',.20,'derived','absorption / thickness',[-1,0,0,0,0]),
        ('mass_cost','单位质量价格','元/kg','cost',.15,'derived','price / areal_density',[3,-1,0,0,1]),
    ]
    for code,title,unit,direction,weight,kind,formula,dims in rows:
        db.add(Criterion(study_id=study.id,code=code,name=title,unit=unit,direction=direction,
                         center_weight=weight,kind=kind,formula=formula,dims=dims,version=1))
    db.flush()

if __name__=='__main__':seed();print('seed insert-only complete')
