import psycopg2
import os


# DATABASE_URL = (
#     "postgresql://postgres.nuoiyydeurtxqtlzwutq:L3H3qy728jNlduwl@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
#     )

DATABASE_URL = "postgresql://postgres.nuoiyydeurtxqtlzwutq:L3H3qy728jNlduwl@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=5
    )
