import os
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('SEED_DEMO', 'false')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.mysql import DOUBLE as MySQLDouble

from src.config.database import Base
from src.config import database as db_module
import src.models  # noqa: F401  ensure all models are registered


@pytest.fixture(scope='session')
def engine():
    from sqlalchemy.dialects import sqlite
    # The models declare MySQL DOUBLE explicitly; compile it as SQLite float.
    MySQLDouble.__visit_name__ = 'FLOAT'
    eng = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, expire_on_commit=False)
    session = Session()
    db_module.Session = Session
    yield session
    session.close()
    transaction.rollback()
    connection.close()
