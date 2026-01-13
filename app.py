import os
import psycopg2


def insert_sample_account():
    """Insert a sample account. Database connection parameters are read from
    environment variables: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_SSLMODE.
    Returns the newly inserted account_id on success.
    """
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "db.nuoiyydeurtxqtlzwutq.supabase.co"),
            port=int(os.getenv("DB_PORT", 5432)),
            dbname=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "CxmZJCnw4qvBsFQE"),
            sslmode=os.getenv("DB_SSLMODE", "require")
        )

        cur = conn.cursor()

        insert_query = """
            INSERT INTO accounts (
                account_code,
                account_type,
                first_name,
                last_name,
                mobile,
                email,
                city,
                state
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING account_id;
        """

        values = (
            "CUST-1002",
            "Customer",
            "Pavan",
            "Gentela",
            "9876543210",
            "pavan@example.com",
            "Hyderabad",
            "Telangana"
        )

        cur.execute(insert_query, values)
        account_id = cur.fetchone()[0]
        conn.commit()

        return account_id

    except Exception:
        if conn:
            conn.rollback()
        raise

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    try:
        aid = insert_sample_account()
        print(f"✅ Record inserted successfully. account_id = {aid}")
    except Exception as e:
        print("❌ Error while inserting record:", e)
