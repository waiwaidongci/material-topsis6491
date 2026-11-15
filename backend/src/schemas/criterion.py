from pydantic import BaseModel,Field,ConfigDict,field_validator,model_validator
from src.constants.enums import Direction
from src.services.derivation.dimensions import DIMENSION_NAMES,is_valid_dims

CODE_PATTERN=r'^[a-z][a-z0-9_]{1,29}$'
class CriterionInput(BaseModel):
    study_id:int
    code:str=Field(min_length=2,max_length=30,pattern=CODE_PATTERN)
    name:str=Field(min_length=1,max_length=100)
    unit:str=Field(min_length=1,max_length=50)
    direction:Direction
    center_weight:float=Field(gt=0,le=1000,allow_inf_nan=False,strict=True)
    kind:str=Field(default='base',pattern='^(base|derived)$')
    formula:str=Field(default='',max_length=600)
    dims:list[int]=Field(default_factory=lambda:[0]*len(DIMENSION_NAMES))
    # Optimistic concurrency: absent on create; required and must match on update.
    # ge=0 lets a deliberately stale version (0) reach the conflict check.
    version:int|None=Field(default=None,ge=0)
    @field_validator('dims')
    @classmethod
    def _dims(cls,v):
        if not is_valid_dims(v):raise ValueError('量纲须为5个整数（length,mass,time,current,currency），指数绝对值不超过12')
        return v
    @model_validator(mode='after')
    def _cross(self):
        if self.kind=='derived' and not self.formula.strip():
            raise ValueError('派生指标必须给出公式')
        if self.kind=='base' and self.formula.strip():
            raise ValueError('基础量指标不携带公式')
        return self
class CriterionOut(BaseModel):
    id:int
    study_id:int
    code:str
    name:str
    unit:str
    direction:Direction
    center_weight:float
    kind:str
    formula:str
    dims:list[int]
    version:int
    model_config=ConfigDict(from_attributes=True)
