from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from datetime import date, timedelta
from db import get_connection
from models5 import (
    AccountCheckRequest, AccountCheckResponse,
    AccountCreateRequest, AccountCreateResponse,
    AccountUpdateRequest,
    ApplicationCreateRequest, ApplicationResponse,
    ApplicationListItem, ApplicationListResponse,
    OrnamentCreateRequest, OrnamentCreateResponse,
    EstimationItemCreateRequest, EstimationResponse,
    PledgeDetailsCreateRequest, PledgeDetailsResponse,
    AddressCreateRequest,
    BankAccountCreateRequest,
    AccountDocumentCreateRequest,
    PaymentInvoiceCreateRequest,
    PaymentInvoiceResponse,
    PaymentInvoiceItemCreateRequest,
    PaymentInvoiceItemResponse,
    PaymentDeductionCreateRequest,
    PaymentDeductionResponse,
    PaymentSettlementCreateRequest,
    PaymentSettlementResponse
)

from gold_calculator import calculate_gold_estimation

app = FastAPI(title="Gold CRM Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------
# COMMON HELPERS
# -------------------------------------------------

def get_account_id(cur, mobile: str) -> int:
    cur.execute(
        "SELECT account_id FROM gold_schema.accounts WHERE mobile = %s",
        (mobile,)
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Account not found")

    if isinstance(row, dict):
        account_id = row.get('account_id')
    else:
        account_id = row[0] if len(row) > 0 else None

    if account_id is None:
        raise HTTPException(404, "Account not found")

    return account_id


# -------------------------------------------------
# HEALTH
# -------------------------------------------------

@app.get("/")
@app.head("/")
def health():
    return {"status": "ok"}


# -------------------------------------------------
# ACCOUNT
# -------------------------------------------------

@app.post("/accounts/check", response_model=AccountCheckResponse)
def check_account(payload: AccountCheckRequest):
    if not payload.mobile and not payload.email:
        raise HTTPException(400, "Either mobile or email required")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT account_id, account_code
            FROM gold_schema.accounts
            WHERE mobile = %s OR email = %s
            LIMIT 1
            """,
            (payload.mobile, payload.email)
        )
        row = cur.fetchone()
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
        cur.execute(
            """
            INSERT INTO gold_schema.accounts (
                account_type, account_code,
                first_name, last_name,
                mobile, phone, email,
                gender, date_of_birth, aadhar_no,
                occupation,
                pan_no,
                source, owner,
                state, district, city, pincode,
                address_text
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING account_id, account_code
            """,
            (
                payload.account_type,
                payload.account_code,
                payload.first_name,
                payload.last_name,
                payload.mobile,
                payload.phone,
                payload.email,
                payload.gender,
                payload.date_of_birth,
                payload.aadhar_no,
                payload.occupation,
                payload.pan_no,
                payload.source,
                payload.owner,
                payload.state,
                payload.district,
                payload.city,
                payload.pincode,
                payload.address_text
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
        raise HTTPException(409, "Account already exists")
    finally:
        cur.close()
        conn.close()


@app.put("/accounts/update", response_model=AccountCreateResponse)
def update_account(payload: AccountUpdateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = None

        if payload.mobile:
            cur.execute(
                "SELECT account_id FROM gold_schema.accounts WHERE mobile=%s",
                (payload.mobile,)
            )
            row = cur.fetchone()
            if row:
                account_id = row[0]

        if not account_id and payload.email:
            cur.execute(
                "SELECT account_id FROM gold_schema.accounts WHERE email=%s",
                (payload.email,)
            )
            row = cur.fetchone()
            if row:
                account_id = row[0]

        if not account_id:
            raise HTTPException(404, "Account not found")

        update_data = payload.dict(exclude_unset=True, exclude={'mobile'})

        if not update_data:
            raise HTTPException(400, "No data provided to update")

        set_clauses = []
        values = []
        for field_name, field_value in update_data.items():
            set_clauses.append(f"{field_name}=%s")
            values.append(field_value)

        values.append(account_id)

        sql = f"UPDATE gold_schema.accounts SET {', '.join(set_clauses)} WHERE account_id=%s"
        cur.execute(sql, tuple(values))

        conn.commit()

        cur.execute("SELECT account_code, first_name, last_name, mobile, email FROM gold_schema.accounts WHERE account_id=%s", (account_id,))
        row = cur.fetchone()

        return {
            "account_id": account_id,
            "account_code": row[0],
            "name": f"{row[1]} {row[2]}",
            "mobile": row[3],
            "email": row[4]
        }
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------
# ADDRESSES
# -------------------------------------------------

@app.post("/accounts/addresses")
def add_address(mobile: str, payload: AddressCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            INSERT INTO gold_schema.addresses (
                account_id, address_type,
                address_line, street,
                city, state, country, pincode
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                account_id,
                payload.address_type,
                payload.address_line,
                payload.street,
                payload.city,
                payload.state,
                payload.country,
                payload.pincode
            )
        )
        conn.commit()
        return {"status": "ADDRESS_SAVED"}
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------
# BANK ACCOUNTS
# -------------------------------------------------

@app.post("/accounts/bank-accounts")
def add_bank_account(mobile: str, payload: BankAccountCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)

        if payload.is_primary:
            cur.execute(
                """
                UPDATE gold_schema.bank_accounts
                SET is_primary = FALSE
                WHERE account_id = %s
                """,
                (account_id,)
            )
        else:
            # if no primary exists, make this one primary automatically
            cur.execute(
                "SELECT 1 FROM gold_schema.bank_accounts WHERE account_id=%s AND is_primary=TRUE",
                (account_id,)
            )
            if not cur.fetchone():
                payload.is_primary = True

        cur.execute(
            """
            INSERT INTO gold_schema.bank_accounts (
                account_id, bank_name, branch,
                account_number, ifsc_code,
                account_holder_name,
                account_holder_type,
                is_primary
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                account_id,
                payload.bank_name,
                payload.branch,
                payload.account_number,
                payload.ifsc_code,
                payload.account_holder_name,
                payload.account_holder_type,
                payload.is_primary
            )
        )
        conn.commit()
        return {"status": "BANK_ACCOUNT_SAVED"}
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------
# DOCUMENT METADATA
# -------------------------------------------------

@app.post("/accounts/documents")
def add_document(mobile: str, payload: AccountDocumentCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        #add other fields from document type if not OTHER

        if payload.document_type.upper() != 'OTHER':
            # if not payload.document_number:
            #     raise HTTPException(400, 'document_number is required for non-OTHER documents')
            if not payload.file_path:
                raise HTTPException(400, 'file_path is required for non-OTHER documents')
            if not payload.file_name:
                raise HTTPException(400, 'file_name is required for non-OTHER documents')

        cur.execute(
            """
            INSERT INTO gold_schema.account_documents (
                account_id, document_type,
                document_number, file_path,
                file_name, file_size_mb
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                account_id,
                payload.document_type,
                payload.document_number,
                payload.file_path,
                payload.file_name,
                payload.file_size_mb
            )
        )
        conn.commit()
        return {"status": "DOCUMENT_SAVED"}
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------
# APPLICATIONS
# -------------------------------------------------

@app.post("/applications/create", response_model=ApplicationResponse)
def create_application(payload: ApplicationCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)
        application_no = payload.application_no

        cur.execute(
            """
            SELECT 1 FROM gold_schema.applications
            WHERE account_id = %s
            AND status IN ('DRAFT','SUBMITTED','APPROVED')
            AND application_no = %s
            """,
            (account_id,application_no)
        )
        if cur.fetchone():
            raise HTTPException(409, "Active application already exists")

        # print(payload)
        # branch = payload.place.strip()
        # if branch not in ('Dilsukhnagar', 'narayanaguda'):
        #     raise HTTPException(400, "branch must be Dilsuknagar or narayanaguda")

        cur.execute(
            """
            INSERT INTO gold_schema.applications (
                account_id, application_type,
                application_date, application_no,
                place, status
            )
            VALUES (%s,%s,%s,%s,%s,'DRAFT')
            RETURNING application_id, application_no, status
            """,
            (
                account_id,
                payload.application_type,
                payload.application_date,
                payload.application_no,
                payload.place
            )
        )
        app_id, app_no, status = cur.fetchone()
        conn.commit()
        return {
            "application_id": app_id,
            "application_no": app_no,
            "status": status
        }
    finally:
        cur.close()
        conn.close()


@app.get("/applications/by-user", response_model=ApplicationListResponse)
def get_applications_by_user(mobile: str = Query(...)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            SELECT application_id, application_no,
                   application_type, application_date,
                   place, total_quantity,
                   total_weight_gms, status, created_at
            FROM gold_schema.applications
            WHERE account_id = %s
            ORDER BY created_at DESC
            """,
            (account_id,)
        )
        rows = cur.fetchall()
        return {
            "mobile": mobile,
            "applications": [
                ApplicationListItem(
                    application_id=r[0],
                    application_no=r[1],
                    application_type=r[2],
                    application_date=r[3],
                    branch=r[4],
                    total_quantity=r[5],
                    total_weight_gms=float(r[6]) if r[6] else None,
                    status=r[7],
                    created_at=str(r[8])
                )
                for r in rows
            ]
        }
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------
# PLEDGE RELEASE DETAILS
# -------------------------------------------------

# @app.post("/applications/pledge-details", response_model=PledgeDetailsResponse)
# def create_pledge_details(payload: PledgeDetailsCreateRequest):
#     conn = get_connection()
#     cur = conn.cursor()
#     try:
#         account_id = get_account_id(cur, payload.mobile)

#         cur.execute(
#             "SELECT first_name, last_name, address_text FROM gold_schema.accounts WHERE account_id = %s",
#             (account_id,)
#         )
#         row = cur.fetchone()
#         if not row:
#             raise HTTPException(404, "Account missing for pledge details")

#         pledger_name = f"{row[0]} {row[1]}".strip()
#         pledger_address = row[2]

#         if not pledger_name or pledger_name == "":
#             # fallback to latest address entry
#             cur.execute(
#                 "SELECT address_line, street, city, state, pincode FROM gold_schema.addresses WHERE account_id=%s ORDER BY created_at DESC LIMIT 1",
#                 (account_id,)
#             )
#             addr = cur.fetchone()
#             if addr:
#                 pledger_address = ", ".join([x for x in addr if x])

#         if not pledger_address:
#             raise HTTPException(400, "Pledger address must be available")

#         cur.execute(
#             """
#             SELECT application_id
#             FROM gold_schema.applications
#             WHERE account_id = %s
#             AND application_type = 'PLEDGE_RELEASE'
#             ORDER BY created_at DESC
#             LIMIT 1
#             """,
#             (account_id,)
#         )
#         row = cur.fetchone()
#         if not row:
#             raise HTTPException(409, "No PLEDGE_RELEASE application found")

#         application_id = row[0]

#         cur.execute(
#             "SELECT 1 FROM gold_schema.pledge_details WHERE application_id=%s",
#             (application_id,)
#         )
#         if cur.fetchone():
#             raise HTTPException(409, "Pledge details already exist")

#         cur.execute(
#             """
#             INSERT INTO gold_schema.pledge_details (
#                 application_id, pledger_name,
#                 pledger_address, financier_name,
#                 branch_name, gold_loan_account_no,
#                 principal_amount, interest_amount,
#                 total_due
#             )
#             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
#             RETURNING pledge_id
#             """,
#             (
#                 application_id,
#                 pledger_name,
#                 pledger_address,
#                 payload.financier_name,
#                 payload.branch_name,
#                 payload.gold_loan_account_no,
#                 payload.principal_amount,
#                 payload.interest_amount,
#                 payload.principal_amount + (payload.interest_amount or 0)
#             )
#         )
#         pledge_id = cur.fetchone()[0]
#         conn.commit()
#         total_due = payload.principal_amount + (payload.interest_amount or 0)
#         return {
#             "application_id": application_id,
#             "pledge_id": pledge_id,
#             "status": "PLEDGE_DETAILS_SAVED",
#             "pledge_amount": payload.principal_amount,
#             "interest_amount": payload.interest_amount or 0,
#             "total_due": total_due
#         }
#     finally:
#         cur.close()
#         conn.close()

@app.post("/applications/pledge-details", response_model=PledgeDetailsResponse)
def create_pledge_details(payload: PledgeDetailsCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)

        cur.execute(
            "SELECT first_name, last_name FROM gold_schema.accounts WHERE account_id = %s",
            (account_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Account missing for pledge details")

        pledger_name = f"{row[0]} {row[1]}".strip()
        pledger_address = payload.pledger_address.strip() if payload.pledger_address else ""

        if not pledger_address:
            raise HTTPException(400, "pledger_address is required")

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
        if not row:
            raise HTTPException(409, "No PLEDGE_RELEASE application found")

        application_id = row[0]

        cur.execute(
            "SELECT 1 FROM gold_schema.pledge_details WHERE application_id=%s",
            (application_id,)
        )
        if cur.fetchone():
            raise HTTPException(409, "Pledge details already exist")

        cur.execute(
            """
            INSERT INTO gold_schema.pledge_details (
                application_id, pledger_name,
                pledger_address, financier_name,
                branch_name, gold_loan_account_no,
                principal_amount, interest_amount,
                total_due
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING pledge_id
            """,
            (
                application_id,
                pledger_name,
                pledger_address,
                payload.financier_name,
                payload.branch_name,
                payload.gold_loan_account_no,
                payload.principal_amount,
                payload.interest_amount,
                payload.principal_amount + (payload.interest_amount or 0)
            )
        )
        pledge_id = cur.fetchone()[0]
        conn.commit()
        total_due = payload.principal_amount + (payload.interest_amount or 0)
        return {
            "application_id": application_id,
            "pledge_id": pledge_id,
            "status": "PLEDGE_DETAILS_SAVED",
            "pledge_amount": payload.principal_amount,
            "interest_amount": payload.interest_amount or 0,
            "total_due": total_due
        }
    finally:
        cur.close()
        conn.close()
# -------------------------------------------------
# ORNAMENTS
# -------------------------------------------------

@app.post("/applications/ornaments", response_model=OrnamentCreateResponse)
def create_ornaments(payload: OrnamentCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)
        cur.execute(
            """
            SELECT application_id, application_no, status
            FROM gold_schema.applications
            WHERE account_id=%s
            AND status IN ('DRAFT','SUBMITTED','APPROVED')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (account_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(409, "No active application")

        application_id, application_no, status = row

        total_qty, total_wt = 0, 0.0
        for item in payload.ornaments:
            cur.execute(
                """
                INSERT INTO gold_schema.ornaments (
                    application_id, item_name,
                    quantity, purity_percentage,
                    approx_weight_gms, item_photo_url
                )
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    application_id,
                    item.item_name,
                    item.quantity,
                    item.purity_percentage,
                    item.approx_weight_gms,
                    item.item_photo_url
                )
            )
            total_qty += item.quantity
            total_wt += float(item.approx_weight_gms or 0)

        cur.execute(
            """
            UPDATE gold_schema.applications
            SET total_quantity=%s,
                total_weight_gms=%s
            WHERE application_id=%s
            """,
            (total_qty, round(total_wt, 3), application_id)
        )
        conn.commit()
        return {
            "application_id": application_id,
            "application_no": application_no,
            "total_quantity": total_qty,
            "total_weight_gms": round(total_wt, 3),
            "status": status
        }
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------
# ESTIMATION
# -------------------------------------------------

@app.post("/estimations/items", response_model=EstimationResponse)
def add_estimation_item(payload: EstimationItemCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)

        cur.execute(
            """
            SELECT application_id
            FROM gold_schema.applications
            WHERE account_id=%s
            AND status IN ('DRAFT','SUBMITTED','APPROVED')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (account_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(409, "No active application")

        application_id = row[0]

        cur.execute(
            """
            SELECT e.estimation_id
            FROM gold_schema.estimation_application_map m
            JOIN gold_schema.estimations e
            ON e.estimation_id=m.estimation_id
            WHERE m.application_id=%s
            """,
            (application_id,)
        )
        row = cur.fetchone()

        if row:
            estimation_id = row[0]
        else:
            cur.execute(
                """
                INSERT INTO gold_schema.estimations (
                    account_id, estimation_date,
                    estimation_no, status
                )
                VALUES (%s, CURRENT_DATE, %s, 'ESTIMATED')
                RETURNING estimation_id
                """,
                (account_id, payload.estimation_no)
            )
            estimation_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO gold_schema.estimation_application_map
                (estimation_id, application_id)
                VALUES (%s,%s)
                """,
                (estimation_id, application_id)
            )

        estimation_net_weight = 0
        estimation_gross_amount = 0
        estimation_net_amount = 0

        if not payload.item_name:
            # auto-populate from ornaments for app
            cur.execute(
                "SELECT application_id FROM gold_schema.applications WHERE account_id=%s AND status IN ('DRAFT','SUBMITTED','APPROVED') ORDER BY created_at DESC LIMIT 1",
                (account_id,)
            )
            app_row = cur.fetchone()
            if not app_row:
                raise HTTPException(409, "No active application")
            application_id = app_row[0]

            cur.execute(
                "SELECT item_name, quantity, purity_percentage, approx_weight_gms "
                "FROM gold_schema.ornaments WHERE application_id=%s",
                (application_id,)
            )
            ornaments = cur.fetchall()
            if not ornaments:
                raise HTTPException(409, "No ornaments available to auto-populate estimation")

            if payload.gold_rate_per_gm is None:
                raise HTTPException(400, "gold_rate_per_gm is required for auto-populated estimation items")
            if payload.stone_weight_gms is None:
                raise HTTPException(400, "stone_weight_gms is required for auto-populated estimation items")
            if payload.deduction_percentage is None:
                raise HTTPException(400, "deduction_percentage is required for auto-populated estimation items")

            for item in ornaments:
                item_name, qty, purity, gross_weight = item
                if gross_weight is None:
                    raise HTTPException(400, "Ornament gross_weight_gms is missing for auto-populated estimation item")

                calc_item = calculate_gold_estimation(
                    gross_weight,
                    payload.stone_weight_gms,
                    purity,
                    payload.gold_rate_per_gm,
                    payload.deduction_percentage
                )

                cur.execute(
                    """
                    INSERT INTO gold_schema.estimation_items (
                        estimation_id, item_name,
                        quantity, gross_weight_gms,
                        stone_weight_gms, net_weight_gms,
                        gold_rate_per_gm, purity_percentage,
                        gross_amount, deduction_percentage,
                        net_amount
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        estimation_id,
                        item_name,
                        qty,
                        gross_weight,
                        payload.stone_weight_gms or 0,
                        calc_item["net_gold_weight"],
                        payload.gold_rate_per_gm,
                        purity,
                        calc_item["gross_amount"],
                        payload.deduction_percentage or 0,
                        calc_item["net_amount"]
                    )
                )

                estimation_net_weight += float(calc_item["net_gold_weight"])
                estimation_gross_amount += float(calc_item["gross_amount"])
                estimation_net_amount += float(calc_item["net_amount"])
        else:
            if payload.gross_weight_gms is None or payload.purity_percentage is None or payload.gold_rate_per_gm is None:
                raise HTTPException(400, "gross_weight_gms, purity_percentage, and gold_rate_per_gm are required for manual estimation item")
            if payload.stone_weight_gms is None:
                raise HTTPException(400, "stone_weight_gms is required for manual estimation item")
            if payload.deduction_percentage is None:
                raise HTTPException(400, "deduction_percentage is required for manual estimation item")

            calc = calculate_gold_estimation(
                payload.gross_weight_gms,
                payload.stone_weight_gms,
                payload.purity_percentage,
                payload.gold_rate_per_gm,
                payload.deduction_percentage
            )

            cur.execute(
                """
                INSERT INTO gold_schema.estimation_items (
                    estimation_id, item_name,
                    quantity, gross_weight_gms,
                    stone_weight_gms, net_weight_gms,
                    gold_rate_per_gm, purity_percentage,
                    gross_amount, deduction_percentage,
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
                    calc["net_gold_weight"],
                    payload.gold_rate_per_gm,
                    payload.purity_percentage,
                    calc["gross_amount"],
                    payload.deduction_percentage,
                    calc["net_amount"]
                )
            )

        cur.execute(
            """
            UPDATE gold_schema.estimations
            SET total_net_amount = (
                SELECT SUM(net_amount)
                FROM gold_schema.estimation_items
                WHERE estimation_id=%s
            )
            WHERE estimation_id=%s
            """,
            (estimation_id, estimation_id)
        )

        conn.commit()
        return {
            "estimation_id": estimation_id,
            "net_weight_gms": estimation_net_weight,
            "gross_amount": estimation_gross_amount,
            "net_amount": estimation_net_amount,
            "status": "ESTIMATED"
        }
    finally:
        cur.close()
        conn.close()


@app.post("/payments/invoice/create", response_model=PaymentInvoiceResponse)
def create_payment_invoice(payload: PaymentInvoiceCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)

        # Get latest application + estimation
        cur.execute("""
            SELECT a.application_id, e.estimation_id
            FROM gold_schema.applications a
            JOIN gold_schema.estimation_application_map m
                ON m.application_id = a.application_id
            JOIN gold_schema.estimations e
                ON e.estimation_id = m.estimation_id
            WHERE a.account_id = %s
            ORDER BY a.created_at DESC
            LIMIT 1
        """, (account_id,))
        row = cur.fetchone()

        if not row:
            raise HTTPException(409, "No application/estimation found")

        application_id, estimation_id = row

        if payload.total_net_amount is None:
            cur.execute("SELECT COALESCE(SUM(net_amount),0) FROM gold_schema.estimation_items WHERE estimation_id=%s", (estimation_id,))
            payload_total = cur.fetchone()[0]
        else:
            payload_total = payload.total_net_amount

        cur.execute("""
            INSERT INTO gold_schema.payment_invoices (
                invoice_no,
                account_id,
                application_id,
                estimation_id,
                invoice_date,
                total_net_amount,
                amount_in_words,
                remarks
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING payment_invoice_id, payment_status
        """, (
            payload.invoice_no,
            account_id,
            application_id,
            estimation_id,
            payload.invoice_date,
            payload_total,
            payload.amount_in_words,
            payload.remarks
        ))

        invoice_id, status = cur.fetchone()
        conn.commit()

        return {
            "payment_invoice_id": invoice_id,
            "invoice_no": payload.invoice_no,
            "payment_status": status
        }

    finally:
        cur.close()
        conn.close()


@app.post("/payments/invoice/item", response_model=PaymentInvoiceItemResponse)
def add_invoice_item(payload: PaymentInvoiceItemCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)

        cur.execute("""
            SELECT payment_invoice_id
            FROM gold_schema.payment_invoices
            WHERE account_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (account_id,))
        row = cur.fetchone()

        if not row:
            raise HTTPException(409, "No invoice found")

        invoice_id = row[0]

        if payload.deductions_amount < 0 or payload.deductions_amount > 100:
            raise HTTPException(400, "deductions_amount must be a percentage between 0 and 100")

        cur.execute("""
            INSERT INTO gold_schema.payment_invoice_items (
                payment_invoice_id,
                item_name,
                weight_before_melting,
                weight_after_melting,
                purity_after_melting,
                gold_rate_per_gm,
                gross_amount,
                deduction_percentage,
                net_amount
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING invoice_item_id
        """, (
            invoice_id,
            payload.item_name,
            payload.weight_before_melting,
            payload.weight_after_melting,
            payload.purity_after_melting,
            payload.gold_rate_per_gm,
            payload.gross_amount,
            payload.deduction_percentage,
            payload.net_amount
        ))

        item_id = cur.fetchone()[0]
        conn.commit()

        return {
            "invoice_item_id": item_id,
            "payment_invoice_id": invoice_id
        }

    finally:
        cur.close()
        conn.close()


# @app.post("/payments/deduction", response_model=PaymentDeductionResponse)
# def add_deduction(payload: PaymentDeductionCreateRequest):
#     conn = get_connection()
#     cur = conn.cursor()
#     try:
#         cur.execute("""
#             INSERT INTO gold_schema.payment_deductions (
#                 invoice_item_id,
#                 deduction_type,
#                 deduction_amount
#             )
#             VALUES (%s,%s,%s)
#             RETURNING deduction_id
#         """, (
#             payload.invoice_item_id,
#             payload.deduction_type,
#             payload.deduction_amount
#         ))

#         deduction_id = cur.fetchone()[0]
#         conn.commit()

#         return {
#             "deduction_id": deduction_id,
#             "invoice_item_id": payload.invoice_item_id
#         }

#     finally:
#         cur.close()
#         conn.close()


@app.post("/payments/settlement", response_model=PaymentSettlementResponse)
def add_settlement(payload: PaymentSettlementCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)

        cur.execute("""
            SELECT payment_invoice_id
            FROM gold_schema.payment_invoices
            WHERE account_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (account_id,))
        row = cur.fetchone()

        if not row:
            raise HTTPException(409, "No invoice found")

        invoice_id = row[0]

        cur.execute("""
            INSERT INTO gold_schema.payment_settlements (
                payment_invoice_id,
                payment_mode,
                paid_amount,
                payment_date
            )
            VALUES (%s,%s,%s,%s)
            RETURNING settlement_id
        """, (
            invoice_id,
            payload.payment_mode,
            payload.paid_amount,
            payload.payment_date
        ))

        settlement_id = cur.fetchone()[0]
        
        # Update application status from DRAFT to SUBMITTED after successful settlement
        cur.execute("""
            UPDATE gold_schema.applications
            SET status = 'SUBMITTED'
            WHERE application_id = (
                SELECT application_id FROM gold_schema.payment_invoices WHERE payment_invoice_id = %s
            )
            AND status = 'DRAFT'
        """, (invoice_id,))
        
        conn.commit()

        return {
            "settlement_id": settlement_id,
            "payment_invoice_id": invoice_id,
            "paid_amount": payload.paid_amount
        }

    finally:
        cur.close()
        conn.close()



@app.get("/applications/final-preview")
def get_final_application_preview(mobile: str = Query(...)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # --------------------------------------------------
        # ACCOUNT (USING MOBILE)
        # --------------------------------------------------
        cur.execute("""
            SELECT *
            FROM gold_schema.accounts
            WHERE mobile = %s
        """, (mobile,))
        account = cur.fetchone()

        if not account:
            raise HTTPException(404, "Account not found")

        account_id = account["account_id"]

        # --------------------------------------------------
        # LATEST ACTIVE APPLICATION
        # --------------------------------------------------
        cur.execute("""
            SELECT *
            FROM gold_schema.applications
            WHERE account_id = %s
              AND status IN ('SUBMITTED', 'APPROVED')
            ORDER BY created_at DESC
            LIMIT 1
        """, (account_id,))
        application = cur.fetchone()

        if not application:
            raise HTTPException(409, "No active application found")

        application_id = application["application_id"]

        # --------------------------------------------------
        # ADDRESSES
        # --------------------------------------------------
        cur.execute("""
            SELECT address_type, address_line, street,
                   city, state, country, pincode
            FROM gold_schema.addresses
            WHERE account_id = %s
        """, (account_id,))
        addresses = cur.fetchall()

        # --------------------------------------------------
        # PRIMARY BANK ACCOUNT
        # --------------------------------------------------
        cur.execute("""
            SELECT bank_name, branch, account_number,
                   ifsc_code, account_holder_name
            FROM gold_schema.bank_accounts
            WHERE account_id = %s
              AND is_primary = TRUE
            LIMIT 1
        """, (account_id,))
        bank_account = cur.fetchone()

        # --------------------------------------------------
        # ORNAMENTS
        # --------------------------------------------------
        cur.execute("""
            SELECT item_name,
                   quantity,
                   purity_percentage,
                   approx_weight_gms,
                   item_photo_url
            FROM gold_schema.ornaments
            WHERE application_id = %s
        """, (application_id,))
        ornaments = cur.fetchall()

        # --------------------------------------------------
        # ESTIMATION + ITEMS
        # --------------------------------------------------
        cur.execute("""
            SELECT e.estimation_id,
                   e.estimation_no,
                   e.estimation_date,
                   e.total_net_amount
            FROM gold_schema.estimation_application_map m
            JOIN gold_schema.estimations e
              ON e.estimation_id = m.estimation_id
            WHERE m.application_id = %s
        """, (application_id,))
        estimation = cur.fetchone()

        estimation_items = []
        if estimation:
            cur.execute("""
                SELECT item_name,
                       quantity,
                       gross_weight_gms,
                       stone_weight_gms,
                       net_weight_gms,
                       gold_rate_per_gm,
                       purity_percentage,
                       gross_amount,
                       deduction_percentage,
                       net_amount
                FROM gold_schema.estimation_items
                WHERE estimation_id = %s
            """, (estimation["estimation_id"],))
            estimation_items = cur.fetchall()

        # --------------------------------------------------
        # PLEDGE DETAILS (ONLY FOR PLEDGE RELEASE)
        # --------------------------------------------------
        cur.execute("""
            SELECT pledger_name,
                   pledger_address,
                   financier_name,
                   branch_name,
                   gold_loan_account_no,
                   principal_amount,
                   interest_amount,
                   total_due,
                   cheque_no,
                   cheque_date,
                   margin_percentage
            FROM gold_schema.pledge_details
            WHERE application_id = %s
        """, (application_id,))
        pledge_details = cur.fetchone()

        # --------------------------------------------------
        # DOCUMENTS
        # --------------------------------------------------
        cur.execute("""
            SELECT document_type,
                   document_number,
                   file_name,
                   file_path
            FROM gold_schema.account_documents
            WHERE account_id = %s
        """, (account_id,))
        documents = cur.fetchall()

        # --------------------------------------------------
        # FINAL RESPONSE
        # --------------------------------------------------
        return {
            "account": {
                "account_id": account_id,
                "account_code": account["account_code"],
                "name": f"{account['first_name']} {account['last_name']}",
                "mobile": account["mobile"],
                "email": account["email"],
                "dob": account["date_of_birth"],
                "gender": account["gender"],
                "pan_no": account["pan_no"],
                "aadhar_no": account["aadhar_no"],
                "occupation": account["occupation"]
            },
            "addresses": addresses,
            "bank_account": bank_account,
            "application": {
                "application_id": application_id,
                "application_no": application["application_no"],
                "application_type": application["application_type"],
                "application_date": application["application_date"],
                "branch": application["place"],
                "status": application["status"],
                "total_quantity": application["total_quantity"],
                "total_weight_gms": float(application["total_weight_gms"] or 0)
            },
            "ornaments": ornaments,
            "estimation": {
                "summary": estimation,
                "items": estimation_items
            },
            "pledge_details": pledge_details,
            "documents": documents
        }

    finally:
        cur.close()
        conn.close()



@app.get("/branches")
def get_branches():
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT branch_code,branch_name,full_address_txt,phone_number FROM gold_schema.branches")
        branches = cur.fetchall()
        return {"branches": branches}
    finally:
        cur.close()
        conn.close()


@app.get("/gold-items")
def get_gold_items():
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, item_name 
            FROM gold_schema.gold_items
            ORDER BY id
        """)
        rows = cur.fetchall()

        gold_items = [
            {"id": row[0], "name": row[1]}
            for row in rows
        ]

        return {"gold_items": gold_items}

    finally:
        cur.close()
        conn.close()


@app.get("/customers/search")
def search_customer(mobile: str = Query(...)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM gold_schema.accounts WHERE mobile=%s", (mobile,))
        customer = cur.fetchone()
        if not customer:
            raise HTTPException(404, "Customer not found")

        account_id = customer['account_id']

        # Fetch all applications
        cur.execute("SELECT * FROM gold_schema.applications WHERE account_id=%s ORDER BY created_at DESC", (account_id,))
        applications = cur.fetchall()

        # Fetch all estimations with items
        cur.execute("""
            SELECT e.*, m.application_id
            FROM gold_schema.estimations e
            JOIN gold_schema.estimation_application_map m ON e.estimation_id=m.estimation_id
            WHERE e.account_id=%s ORDER BY e.estimation_date DESC
        """, (account_id,))
        estimations = cur.fetchall()
        for est in estimations:
            cur.execute("SELECT * FROM gold_schema.estimation_items WHERE estimation_id=%s", (est['estimation_id'],))
            est['items'] = cur.fetchall()

        # Fetch all invoices with items and settlements
        cur.execute("SELECT * FROM gold_schema.payment_invoices WHERE account_id=%s ORDER BY created_at DESC", (account_id,))
        invoices = cur.fetchall()
        for inv in invoices:
            invoice_id = inv['payment_invoice_id']
            cur.execute("SELECT * FROM gold_schema.payment_invoice_items WHERE payment_invoice_id=%s", (invoice_id,))
            inv['items'] = cur.fetchall()
            cur.execute("SELECT * FROM gold_schema.payment_settlements WHERE payment_invoice_id=%s ORDER BY payment_date DESC", (invoice_id,))
            inv['settlements'] = cur.fetchall()

        # Fetch all addresses
        cur.execute("SELECT * FROM gold_schema.addresses WHERE account_id=%s", (account_id,))
        addresses = cur.fetchall()

        # Fetch all bank accounts
        cur.execute("SELECT * FROM gold_schema.bank_accounts WHERE account_id=%s", (account_id,))
        bank_accounts = cur.fetchall()

        # Fetch all documents
        cur.execute("SELECT * FROM gold_schema.account_documents WHERE account_id=%s", (account_id,))
        documents = cur.fetchall()

        return {
            "customer": customer,
            "applications": applications,
            "estimations": estimations,
            "invoices": invoices,
            "addresses": addresses,
            "bank_accounts": bank_accounts,
            "documents": documents
        }
    finally:
        cur.close()
        conn.close()


@app.get("/transactions/all")
def get_transactions(
    mobile: str = Query(None),
    start_date: date = Query(None),
    end_date: date = Query(None),
    days: int = Query(None)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        account_condition = ""
        params = []

        if mobile:
            account_id = get_account_id(cur, mobile)
            account_condition = "AND account_id = %s"
            params.append(account_id)

        if days is not None:
            end_date = date.today()
            start_date = date.today() - timedelta(days=days)

        if start_date is not None and end_date is not None:
            account_condition += " AND invoice_date BETWEEN %s AND %s"
            params.extend([start_date, end_date])

        invoices_sql = f"SELECT * FROM gold_schema.payment_invoices WHERE 1=1 {account_condition} ORDER BY invoice_date DESC"
        cur.execute(invoices_sql, tuple(params))
        invoices = cur.fetchall()

        invoice_ids = [r['payment_invoice_id'] for r in invoices]

        item_params = []
        settlements_params = []
        cond_items = ""
        cond_settlements = ""

        if invoice_ids:
            cond_items = "WHERE payment_invoice_id = ANY(%s)"
            item_params = [invoice_ids]
            cond_settlements = "WHERE payment_invoice_id = ANY(%s)"
            settlements_params = [invoice_ids]

        cur.execute(f"SELECT * FROM gold_schema.payment_invoice_items {cond_items}", tuple(item_params))
        items = cur.fetchall()

        cur.execute(f"SELECT * FROM gold_schema.payment_settlements {cond_settlements} ORDER BY payment_date DESC", tuple(settlements_params))
        settlements = cur.fetchall()

        total_invoice_amount = sum(float(r.get('total_net_amount') or 0) for r in invoices)
        total_settled_amount = sum(float(r.get('paid_amount') or 0) for r in settlements)

        return {
            "invoices": invoices,
            "invoice_items": items,
            "settlements": settlements,
            "summary": {
                "total_invoices": len(invoices),
                "total_invoice_amount": total_invoice_amount,
                "total_settled_amount": total_settled_amount
            }
        }
    finally:
        cur.close()
        conn.close()


@app.get("/estimations/by-user")
def get_estimations_by_user(mobile: str = Query(...)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        account_id = get_account_id(cur, mobile)

        cur.execute("SELECT * FROM gold_schema.estimations WHERE account_id=%s ORDER BY estimation_date DESC", (account_id,))
        estimations = cur.fetchall()

        for est in estimations:
            cur.execute("SELECT * FROM gold_schema.estimation_items WHERE estimation_id=%s", (est['estimation_id'],))
            est['items'] = cur.fetchall()

        return {
            "estimations": estimations
        }
    finally:
        cur.close()
        conn.close()

