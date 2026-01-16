import psycopg2
import os


DATABASE_URL = (
    "postgresql://postgres.nuoiyydeurtxqtlzwutq:CxmZJCnw4qvBsFQE@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
    )
def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=5
    )
