from fastapi import FastAPI, HTTPException, Query
import psycopg2
from db import get_connection
from models import AccountCreateRequest, AccountCreateResponse, AccountCheckRequest,AccountCheckResponse, ApplicationCreateRequest, ApplicationResponse, ApplicationListItem, ApplicationListResponse,  OrnamentCreateRequest, OrnamentCreateResponse, EstimationItemCreateRequest, EstimationResponse,PledgeDetailsCreateRequest, PledgeDetailsResponse



from gold_calculator import calculate_gold_estimation
app = FastAPI(title="Account Service")

# ✅ Health check (Render-safe)
@app.get("/")
@app.head("/")
def health():
    return {"status": "ok"}

@app.post("/accounts/check", response_model=AccountCheckResponse)
def check_account(payload: AccountCheckRequest):

    if not payload.mobile and not payload.email:
        raise HTTPException(
            status_code=400,
            detail="Either mobile or email is required"
        )

    conn = get_connection()
    cur = conn.cursor()

    try:
        query = """
            SELECT account_id, account_code
            FROM gold_schema.accounts
            WHERE mobile = %s OR email = %s
            LIMIT 1;
        """

        cur.execute(query, (payload.mobile, payload.email))
        row = cur.fetchone()
        print("row:",row)

        if row:
            return {
                "exists": True,
                "account_id": row[0],
                "account_code": row[1]
            }

        return {"exists": False}

    finally:
        cur.close()
        conn.close()

@app.post("/accounts/create", response_model=AccountCreateResponse)
def create_account(payload: AccountCreateRequest):

    conn = get_connection()
    cur = conn.cursor()

    try:
        insert_query = """
            INSERT INTO gold_schema.accounts (
                account_type,
                account_code,
                first_name,
                last_name,
                mobile,
                email,
                city,
                state
            )
            VALUES (%s, %s,%s, %s, %s, %s, %s, %s)
            RETURNING account_id, account_code;
        """

        cur.execute(
            insert_query,
            (
                payload.account_type,
                payload.account_code,
                payload.first_name,
                payload.last_name,
                payload.mobile,
                payload.email,
                payload.city,
                payload.state
            )
        )

        account_id, account_code = cur.fetchone()
        conn.commit()

        return {
            "account_id": account_id,
            "account_code": account_code,
            "name": f"{payload.first_name} {payload.last_name}",
            "mobile": payload.mobile,
            "email": payload.email
        }

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail="Account already exists"
        )

    finally:
        cur.close()
        conn.close()

@app.get("/applications/by-user", response_model=ApplicationListResponse)
def get_applications_by_user(
    mobile: str = Query(..., min_length=10, max_length=15)
):
    conn = get_connection()
    cur = conn.cursor()

    try:
        # 1️⃣ Validate account exists
        cur.execute(
            """
            SELECT account_id
            FROM gold_schema.accounts
            WHERE mobile = %s
            """,
            (mobile,)
        )

        account_row = cur.fetchone()
        if not account_row:
            raise HTTPException(
                status_code=404,
                detail="Account not found for given mobile"
            )

        account_id = account_row[0]

        # 2️⃣ Fetch applications
        cur.execute(
            """
            SELECT
                a.application_id,
                a.application_no,
                a.application_type,
                a.application_date,
                a.place,
                a.total_quantity,
                a.total_weight_gms,
                a.status,
                a.created_at
            FROM gold_schema.applications a
            WHERE a.account_id = %s
            ORDER BY a.created_at DESC
            """,
            (account_id,)
        )

        rows = cur.fetchall()

        applications = [
            ApplicationListItem(
                application_id=row[0],
                application_no=row[1],
                application_type=row[2],
                application_date=row[3],
                place=row[4],
                total_quantity=row[5],
                total_weight_gms=float(row[6]) if row[6] is not None else None,
                status=row[7],
                created_at=str(row[8])
            )
            for row in rows
        ]

        return {
            "mobile": mobile,
            "applications": applications
        }

    finally:
        cur.close()
        conn.close()

@app.post("/applications/create", response_model=ApplicationResponse)
def create_application(payload: ApplicationCreateRequest):

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 1️⃣ Validate account exists
        cur.execute(
            "SELECT account_id  FROM gold_schema.accounts WHERE mobile = %s",
            (payload.mobile,)
        )
        account_id = cur.fetchone()[0]
        print("account_id:",account_id)
        if not account_id:
            raise HTTPException(
                status_code=404,
                detail="Account not found"
            )

        # 2️⃣ Insert application
        insert_query = f"""
            INSERT INTO gold_schema.applications (
                account_id,
                application_type,
                application_date,
                application_no,
                place,
                status
            )
            VALUES ({account_id}, %s, %s, %s, %s, %s)
            RETURNING application_id, application_no, status;
        """
        #         total_quantity,
        #         total_weight_gms,

        print("insert_query:",insert_query)

        cur.execute(
            insert_query,
            (
                #payload.account_id,
                payload.application_type,
                payload.application_date,
                payload.application_no,
                payload.place,
                "SUBMITTED"
            )
        )
        #print("Executed insert_query",cur.fetchone())
                #         payload.total_quantity,
                # payload.total_weight_gms,
        application_id, application_no, status = cur.fetchone()
        conn.commit()

        return {
            "application_id": application_id,
            "application_no": application_no,
            "status": status
        }

    except HTTPException:
        raise

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if conn:
            cur.close()
            conn.close()

@app.post("/applications/pledge-details",response_model=PledgeDetailsResponse
)
def create_pledge_details(payload: PledgeDetailsCreateRequest):

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 1️⃣ Resolve account from mobile
        cur.execute(
            """
            SELECT account_id
            FROM gold_schema.accounts
            WHERE mobile = %s
            """,
            (payload.mobile,)
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, "Account not found")

        account_id = row[0]

        # 2️⃣ Resolve latest PLEDGE application
        cur.execute(
            """
            SELECT application_id
            FROM gold_schema.applications
            WHERE account_id = %s
              AND application_type = 'PLEDGE_RELEASE'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (account_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(
                409,
                "No PLEDGE_RELEASE application found for this mobile"
            )

        application_id = row[0]

        # 3️⃣ Ensure pledge details not already created
        cur.execute(
            """
            SELECT 1
            FROM gold_schema.pledge_details
            WHERE application_id = %s
            """,
            (application_id,)
        )
        if cur.fetchone():
            raise HTTPException(
                409,
                "Pledge details already exist for this application"
            )

        # 4️⃣ Insert pledge details
        cur.execute(
            """
            INSERT INTO gold_schema.pledge_details (
                application_id,
                pledger_name,
                pledger_address,
                financier_name,
                branch_name,
                gold_loan_account_no,
                authorized_person,
                principal_amount,
                interest_amount,
                total_due,
                cheque_no,
                cheque_date,
                margin_percentage
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING pledge_id
            """,
            (
                application_id,
                payload.pledger_name,
                payload.pledger_address,
                payload.financier_name,
                payload.branch_name,
                payload.gold_loan_account_no,
                payload.authorized_person,
                payload.principal_amount,
                payload.interest_amount,
                payload.total_due,
                payload.cheque_no,
                payload.cheque_date,
                payload.margin_percentage
            )
        )

        pledge_id = cur.fetchone()[0]

        conn.commit()

        return {
            "application_id": application_id,
            "pledge_id": pledge_id,
            "status": "PLEDGE_DETAILS_SAVED"
        }

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        if conn:
            cur.close()
            conn.close()






@app.post("/applications/ornaments",response_model=OrnamentCreateResponse)
def create_ornaments(payload: OrnamentCreateRequest):

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 1️⃣ Resolve account from mobile
        cur.execute(
            """
            SELECT account_id
            FROM gold_schema.accounts
            WHERE mobile = %s
            """,
            (payload.mobile,)
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, "Account not found for mobile")

        account_id = row[0]

        # 2️⃣ Resolve latest active application
        cur.execute(
            """
            SELECT application_id, application_no, status
            FROM gold_schema.applications
            WHERE account_id = %s
              AND status IN ('SUBMITTED', 'APPROVED')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (account_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(
                409,
                "No active application found for this mobile"
            )

        print("get active app:",row)
        application_id, application_no, status = row

        # 3️⃣ Insert ornaments + calculate totals
        total_quantity = 0
        total_weight = 0.0

        insert_sql = """
            INSERT INTO gold_schema.ornaments (
                application_id,
                item_name,
                quantity,
                purity_percentage,
                approx_weight_gms,
                item_photo_url
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """

        for item in payload.ornaments:
            if item.quantity <= 0:
                raise HTTPException(
                    400,
                    f"Invalid quantity for item {item.item_name}"
                )

            cur.execute(
                insert_sql,
                (
                    application_id,
                    item.item_name,
                    item.quantity,
                    item.purity_percentage,
                    item.approx_weight_gms,
                    item.item_photo_url
                )
            )

            total_quantity += item.quantity
            total_weight += item.approx_weight_gms or 0

        # 4️⃣ Update application totals
        cur.execute(
            """
            UPDATE gold_schema.applications
            SET total_quantity = %s,
                total_weight_gms = %s
            WHERE application_id = %s
            """,
            (
                total_quantity,
                round(total_weight, 3),
                application_id
            )
        )

        conn.commit()

        return {
            "application_id": application_id,
            "application_no": application_no,
            "total_quantity": total_quantity,
            "total_weight_gms": round(total_weight, 3),
            "status": status
        }

    except HTTPException:
        raise

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if conn:
            cur.close()
            conn.close()

@app.post("/estimations/items", response_model=EstimationResponse)
def add_estimation_item(payload: EstimationItemCreateRequest):

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 1️⃣ Resolve account
        cur.execute(
            """
            SELECT account_id
            FROM gold_schema.accounts
            WHERE mobile = %s
            """,
            (payload.mobile,)
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, "Account not found")

        account_id = row[0]

        # 2️⃣ Resolve active application
        cur.execute(
            """
            SELECT application_id
            FROM gold_schema.applications
            WHERE account_id = %s
              AND status IN ('SUBMITTED', 'APPROVED')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (account_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(409, "No active application found")

        application_id = row[0]

        # 3️⃣ Check existing estimation
        cur.execute(
            """
            SELECT e.estimation_id
            FROM gold_schema.estimation_application_map m
            JOIN gold_schema.estimations e
              ON m.estimation_id = e.estimation_id
            WHERE m.application_id = %s
            """,
            (application_id,)
        )
        row = cur.fetchone()

        if row:
            estimation_id = row[0]
        else:
            # ✅ MANUAL estimation_no INSERT (FIXED placeholders)
            cur.execute(
                """
                INSERT INTO gold_schema.estimations (
                    account_id,
                    estimation_date,
                    estimation_no,
                    status
                )
                VALUES (%s, CURRENT_DATE, %s, 'ESTIMATED')
                RETURNING estimation_id
                """,
                (account_id, payload.estimation_no)
            )

            result = cur.fetchone()
            if result is None:
                raise HTTPException(500, "Failed to create estimation")

            estimation_id = result[0]

            # map estimation ↔ application
            cur.execute(
                """
                INSERT INTO gold_schema.estimation_application_map (
                    estimation_id,
                    application_id
                )
                VALUES (%s, %s)
                """,
                (estimation_id, application_id)
            )

        # 4️⃣ Calculate gold values
        # net_gold_weight, gross_amount, net_amount = calculate_gold_estimation(
        #     payload.gross_weight_gms,
        #     payload.stone_weight_gms,
        #     payload.purity_percentage,
        #     payload.gold_rate_per_gm,
        #     payload.deductions_amount
        # )
        calc = calculate_gold_estimation(
        payload.gross_weight_gms,
        payload.stone_weight_gms,
        payload.purity_percentage,
        payload.gold_rate_per_gm,
        payload.deduction_percentage
    )
        print("calculation result:",calc)
        net_gold_weight = calc["net_gold_weight"]
        gross_amount = calc["gross_amount"]
        net_amount = calc["net_amount"]

        # 5️⃣ Insert estimation item
        cur.execute(
            """
            INSERT INTO gold_schema.estimation_items (
                estimation_id,
                item_name,
                quantity,
                gross_weight_gms,
                stone_weight_gms,
                net_weight_gms,
                gold_rate_per_gm,
                purity_percentage,
                gross_amount,
                deduction_percentage,
                net_amount
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                estimation_id,
                payload.item_name,
                payload.quantity,
                payload.gross_weight_gms,
                payload.stone_weight_gms,
                net_gold_weight,
                payload.gold_rate_per_gm,
                payload.purity_percentage,
                gross_amount,
                payload.deduction_percentage,
                net_amount
            )
        )

        conn.commit()

        return {
            "estimation_id": estimation_id,
            "net_weight_gms": net_gold_weight,
            "gross_amount": gross_amount,
            "net_amount": net_amount,
            "status": "ESTIMATED"
        }

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        if conn:
            cur.close()
            conn.close()
