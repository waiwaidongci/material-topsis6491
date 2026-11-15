from sqlalchemy import String,UniqueConstraint
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import Mapped,mapped_column,relationship
from src.config.database import Base
class MaterialSample(Base):
    __tablename__='material_samples'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(40),unique=True)
    name:Mapped[str]=mapped_column(String(100))
    family:Mapped[str]=mapped_column(String(100))
    # Legacy five fixed columns: retained for migrated trade-offs and trial plans.
    # Nullable so newly defined base quantities can be recorded-missing instead.
    absorption:Mapped[float|None]=mapped_column(DOUBLE(asdecimal=False),nullable=True)
    impact:Mapped[float|None]=mapped_column(DOUBLE(asdecimal=False),nullable=True)
    carbon:Mapped[float|None]=mapped_column(DOUBLE(asdecimal=False),nullable=True)
    price:Mapped[float|None]=mapped_column(DOUBLE(asdecimal=False),nullable=True)
    thickness:Mapped[float|None]=mapped_column(DOUBLE(asdecimal=False),nullable=True)
    batch:Mapped[str]=mapped_column(String(100),default='')
    measurement_rows:Mapped[list['SampleMeasurement']]=relationship(
        backref='sample_ref',cascade='all, delete-orphan',lazy='selectin')
