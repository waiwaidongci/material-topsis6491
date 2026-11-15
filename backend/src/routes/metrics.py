from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.auth import current_user,editor
from src.schemas.metric import BaseMetricInput,BaseMetricOut,MeasurementIn,MeasurementOut
from src.controllers import metric_controller as controller
router=APIRouter(prefix='/metrics',tags=['metrics'])
@router.get('',response_model=list[BaseMetricOut])
def index(study_id:int,db=Depends(get_db),user=Depends(current_user)):return controller.list_metrics(db,study_id)
@router.post('',response_model=BaseMetricOut,status_code=201)
def create(data:BaseMetricInput,db=Depends(get_db),user=Depends(editor)):return controller.create_metric(db,data)
@router.put('/{id}',response_model=BaseMetricOut)
def update(id:int,data:BaseMetricInput,db=Depends(get_db),user=Depends(editor)):return controller.update_metric(db,id,data)
@router.get('/measurements',response_model=list[MeasurementOut])
def measurements(study_id:int,db=Depends(get_db),user=Depends(current_user)):return controller.list_measurements(db,study_id)
@router.put('/samples/{sample_id}/measurements/{metric_code}',response_model=MeasurementOut)
def set_measurement(sample_id:int,metric_code:str,data:MeasurementIn,db=Depends(get_db),user=Depends(editor)):
    value=data.values.get('value')
    controller.upsert_measurement(db,sample_id,metric_code,value)
    return {'sample_id':sample_id,'metric_code':metric_code,'value':value}
@router.get('/preview')
def preview(study_id:int,db=Depends(get_db),user=Depends(current_user)):return controller.preview(db,study_id)
