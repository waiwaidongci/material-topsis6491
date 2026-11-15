from datetime import datetime
from sqlalchemy import String,ForeignKey,UniqueConstraint,DateTime,JSON,Integer,Text
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class DerivedValue(Base):
    """Cached derived result per sample/criterion, with provenance trace."""
    __tablename__='derived_values'
    id:Mapped[int]=mapped_column(primary_key=True)
    criterion_id:Mapped[int]=mapped_column(ForeignKey('criteria.id'))
    sample_id:Mapped[int]=mapped_column(ForeignKey('material_samples.id'))
    value:Mapped[float|None]=mapped_column(DOUBLE(asdecimal=False),nullable=True)
    trace:Mapped[dict]=mapped_column(JSON,default=dict)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint('criterion_id','sample_id'),)
