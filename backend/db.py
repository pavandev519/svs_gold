import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import os


# DATABASE_URL = (
#     "postgresql://postgres.nuoiyydeurtxqtlzwutq:L3H3qy728jNlduwl@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
# )

DATABASE_URL = "postgresql://neondb_owner:npg_fZ34VQeJLgON@ep-lively-haze-ahmx92ro-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# DATABASE_URL = "postgresql://postgres.nuoiyydeurtxqtlzwutq:L3H3qy728jNlduwl@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

connection_pool = ThreadedConnectionPool(
    1,
    20,
    DATABASE_URL,
    connect_timeout=5
)

class PooledConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        try:
            connection_pool.putconn(self._conn)
        except Exception:
            self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_connection():
    return PooledConnection(connection_pool.getconn())
