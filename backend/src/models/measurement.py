from sqlalchemy import String,ForeignKey,UniqueConstraint
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class SampleMeasurement(Base):
    """One base-quantity measurement for one sample; NULL means recorded-missing."""
    __tablename__='sample_measurements'
    id:Mapped[int]=mapped_column(primary_key=True)
    sample_id:Mapped[int]=mapped_column(ForeignKey('material_samples.id'))
    metric_code:Mapped[str]=mapped_column(String(30))
    value:Mapped[float|None]=mapped_column(DOUBLE(asdecimal=False),nullable=True)
    __table_args__=(UniqueConstraint('sample_id','metric_code'),)
