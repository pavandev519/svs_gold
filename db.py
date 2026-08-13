import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import os

##Pavan Neon###
#DATABASE_URL = "postgresql://neondb_owner:npg_fZ34VQeJLgON@ep-lively-haze-ahmx92ro-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

##Vinay SVS Neon##
DATABASE_URL = "postgresql://neondb_owner:npg_BxIQGM2VNqy7@ep-mute-field-an95n0jb-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

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
    conn = connection_pool.getconn()
    if conn.closed:
        try:
            connection_pool.putconn(conn, close=True)
        except Exception:
            pass
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")
    return PooledConnection(conn)
