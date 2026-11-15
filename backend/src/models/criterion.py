from sqlalchemy import String,ForeignKey,UniqueConstraint,Integer,JSON
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class Criterion(Base):
    __tablename__='criteria'
    id:Mapped[int]=mapped_column(primary_key=True)
    study_id:Mapped[int]=mapped_column(ForeignKey('candidate_studies.id'))
    code:Mapped[str]=mapped_column(String(30))
    name:Mapped[str]=mapped_column(String(100))
    unit:Mapped[str]=mapped_column(String(50))
    direction:Mapped[str]=mapped_column(String(20))
    center_weight:Mapped[float]=mapped_column(DOUBLE(asdecimal=False))
    # kind: 'base' reads sample measurements; 'derived' is computed from a formula.
    kind:Mapped[str]=mapped_column(String(20),default='base')
    formula:Mapped[str]=mapped_column(String(600),default='')
    # Five integer exponents: length, mass, time, current, currency.
    dims:Mapped[list]=mapped_column(JSON,default=list)
    # Optimistic-concurrency token; every accepted definition edit bumps it.
    version:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('study_id','code'),)
