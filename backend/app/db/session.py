from sqlmodel import Session, create_engine

from app.core.config import settings

# pool_pre_ping: managed Postgres (Neon, and any provider fronted by a
# connection pooler) can silently close an idle connection server-side.
# Without this, SQLAlchemy hands out the dead connection, the query fails,
# and only then does it reconnect - paying the connection cost anyway but
# after a failed round trip first. A cheap `SELECT 1` before each checkout
# catches that up front instead.
# pool_recycle: proactively retire connections before they hit that idle
# limit, rather than relying on pre_ping to catch every case.
engine = create_engine(
    settings.database_url, echo=False, pool_pre_ping=True, pool_recycle=280
)


def get_session():
    with Session(engine) as session:
        yield session
