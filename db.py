import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2 import OperationalError
import os

##Pavan Neon###
#DATABASE_URL = "postgresql://neondb_owner:npg_fZ34VQeJLgON@ep-lively-haze-ahmx92ro-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

##Vinay SVS Neon##
DATABASE_URL = "postgresql://neondb_owner:npg_BxIQGM2VNqy7@ep-mute-field-an95n0jb-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

KEEPALIVE_OPTS = dict(
    connect_timeout=5,
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5,
)

connection_pool = ThreadedConnectionPool(
    1,
    20,
    DATABASE_URL,
    **KEEPALIVE_OPTS
)

class PooledConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        # Return a wrapped cursor that can retry once on OperationalError
        # to recover from transient SSL closures.
        # Preserve any cursor args/kwargs (e.g. cursor_factory=RealDictCursor)
        return CursorWrapper(self, *args, **kwargs)

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


class CursorWrapper:
    def __init__(self, pooled_conn: PooledConnection, *args, **kwargs):
        self._pooled = pooled_conn
        self._conn = pooled_conn._conn
        self._cur = self._conn.cursor(*args, **kwargs)

    def _refresh_connection(self):
        try:
            try:
                connection_pool.putconn(self._conn, close=True)
            except Exception:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._conn = psycopg2.connect(DATABASE_URL, **KEEPALIVE_OPTS, sslmode="require")
            self._pooled._conn = self._conn
            self._cur = self._conn.cursor()
        except Exception:
            raise

    def execute(self, sql, params=None):
        try:
            return self._cur.execute(sql, params)
        except OperationalError:
            # Try once to refresh the connection and re-run the query
            self._refresh_connection()
            return self._cur.execute(sql, params)

    def executemany(self, sql, param_list):
        try:
            return self._cur.executemany(sql, param_list)
        except OperationalError:
            self._refresh_connection()
            return self._cur.executemany(sql, param_list)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size)

    def close(self):
        try:
            return self._cur.close()
        except Exception:
            pass

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def __getattr__(self, name):
        return getattr(self._cur, name)


def get_connection():
    conn = connection_pool.getconn()
    # Validate the connection returned from the pool. If it's closed or
    # otherwise not usable (server may have closed it), replace with a
    # fresh connection to avoid `SSL connection has been closed unexpectedly`.
    try:
        if conn.closed:
            raise Exception("connection.closed")
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
    except Exception:
        try:
            connection_pool.putconn(conn, close=True)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
        conn = psycopg2.connect(DATABASE_URL, **{**KEEPALIVE_OPTS, "connect_timeout": 10}, sslmode="require")
    return PooledConnection(conn)
