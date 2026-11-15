from pydantic import BaseModel,Field,ConfigDict
from src.services.derivation.dimensions import DIMENSION_NAMES
class BaseMetricInput(BaseModel):
    study_id:int
    code:str=Field(min_length=2,max_length=30,pattern=r'^[a-z][a-z0-9_]{1,29}$')
    name:str=Field(min_length=1,max_length=100)
    unit:str=Field(min_length=1,max_length=50)
    dims:list[int]=Field(min_length=5,max_length=5)
    version:int|None=Field(default=None,ge=1)
class BaseMetricOut(BaseModel):
    id:int
    study_id:int
    code:str
    name:str
    unit:str
    dims:list[int]
    version:int
    model_config=ConfigDict(from_attributes=True)
class MeasurementIn(BaseModel):
    # metric_code -> value; null is an explicit recorded-missing entry.
    values:dict[str,float|None]=Field(default_factory=dict)
class MeasurementOut(BaseModel):
    sample_id:int
    metric_code:str
    value:float|None
    model_config=ConfigDict(from_attributes=True)
