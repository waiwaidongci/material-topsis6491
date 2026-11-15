from pydantic import BaseModel,Field,ConfigDict
# Legacy five fixed columns stay nullable so migrated samples keep working while
# newly defined base quantities may be recorded as missing.
class SampleInput(BaseModel):
    code:str=Field(min_length=2,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=2,max_length=100)
    family:str=Field(min_length=1,max_length=100)
    absorption:float|None=Field(default=None,ge=0,le=1,allow_inf_nan=False)
    impact:float|None=Field(default=None,ge=0,le=1000,allow_inf_nan=False)
    carbon:float|None=Field(default=None,ge=0,le=1000,allow_inf_nan=False)
    price:float|None=Field(default=None,ge=0,le=10000,allow_inf_nan=False)
    thickness:float|None=Field(default=None,ge=0,le=1000,allow_inf_nan=False)
    batch:str=Field(default='',max_length=100)
    # Extra research-defined base measurements: code -> value|null.
    measurements:dict[str,float|None]=Field(default_factory=dict)
class SampleOut(BaseModel):
    id:int
    code:str
    name:str
    family:str
    absorption:float|None
    impact:float|None
    carbon:float|None
    price:float|None
    thickness:float|None
    batch:str
    measurements:dict[str,float|None]=Field(default_factory=dict)
    model_config=ConfigDict(from_attributes=True)
