import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from backend.core.config import DATABASE_URL
from backend.models.user import Base
from backend.models.meeting import Meeting  # noqa: F401
from backend.models.participant import Participant  # noqa: F401
from backend.models.notes import Note  # noqa: F401
from backend.models.password_reset_token import PasswordResetToken  # noqa: F401

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

    # Lightweight schema evolution for production safety when running without Alembic.
    # Keeps existing deployments compatible with newly added auth-security fields.
    insp = inspect(engine)
    user_columns = {col["name"] for col in insp.get_columns("users")}

    if "password_updated_at" not in user_columns:
        dialect = engine.dialect.name
        if dialect.startswith("postgres"):
            column_type = "TIMESTAMP WITH TIME ZONE"
        else:
            column_type = "DATETIME"

        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users "
                    f"ADD COLUMN password_updated_at {column_type} NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE users SET password_updated_at = created_at "
                    "WHERE password_updated_at IS NULL"
                )
            )
