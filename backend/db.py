import psycopg2
import os


# DATABASE_URL = (
#     "postgresql://postgres.nuoiyydeurtxqtlzwutq:L3H3qy728jNlduwl@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
#     )

DATABASE_URL = "postgresql://neondb_owner:npg_fZ34VQeJLgON@ep-lively-haze-ahmx92ro-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# DATABASE_URL = "postgresql://postgres.nuoiyydeurtxqtlzwutq:L3H3qy728jNlduwl@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=5
    )
