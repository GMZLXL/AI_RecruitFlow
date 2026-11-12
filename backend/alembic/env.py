from sqlalchemy import create_engine

from alembic import context
from app.db import DATABASE_URL, Base

config = context.config
target_metadata = Base.metadata
url = config.attributes.get("database_url", DATABASE_URL)


def migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrations(config.attributes["connection"])
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        migrations(connection)
    engine.dispose()
