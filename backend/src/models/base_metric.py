from datetime import datetime
from sqlalchemy import String,ForeignKey,UniqueConstraint,DateTime,JSON,Integer
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class BaseMetric(Base):
    """Research-defined base quantity: identity, display unit and dimensions."""
    __tablename__='base_metrics'
    id:Mapped[int]=mapped_column(primary_key=True)
    study_id:Mapped[int]=mapped_column(ForeignKey('candidate_studies.id'))
    code:Mapped[str]=mapped_column(String(30))
    name:Mapped[str]=mapped_column(String(100))
    unit:Mapped[str]=mapped_column(String(50))
    dims:Mapped[list]=mapped_column(JSON)
    version:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('study_id','code'),)
