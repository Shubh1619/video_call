import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.core.config import DATABASE_URL
from backend.models.user import Base
from backend.models.meeting import Meeting  # noqa: F401
from backend.models.participant import Participant  # noqa: F401
from backend.models.notes import Note  # noqa: F401

# SSL CA certificate
ssl_ca_path = os.getenv("TIDB_SSL_CA_PATH", os.path.join(os.path.dirname(__file__), "isrgrootx1.pem"))

engine = create_engine(
    DATABASE_URL,
    pool_size=5,          # max 5 persistent connections
    max_overflow=10,      # extra temporary connections
    pool_timeout=30,      # wait before failing
    pool_pre_ping=True,   # keep connections alive
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Function to create tables
def init_db():
    Base.metadata.create_all(bind=engine)
