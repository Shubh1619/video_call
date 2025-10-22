from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.core.config import DATABASE_URL,MY_DOMAIN
from backend.models.user import Base  # Only import Base from user.py
import os

# Path to SSL CA certificate
ssl_ca_path = os.path.join(os.path.dirname(__file__), "isrgrootx1.pem")

# Create engine with SSL
engine = create_engine(
    DATABASE_URL,
    connect_args={"ssl": {"ca": ssl_ca_path}}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Automatically create tables on app start
def init_db():
    Base.metadata.create_all(bind=engine)
