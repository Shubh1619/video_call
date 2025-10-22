import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.core.config import DATABASE_URL
from backend.models.user import Base  # Only import Base from user.py

# SSL CA certificate
ssl_ca_path = os.getenv("TIDB_SSL_CA_PATH", os.path.join(os.path.dirname(__file__), "isrgrootx1.pem"))

# SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"ssl": {"ca": ssl_ca_path}},
    pool_pre_ping=True,  # avoids stale connections
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
