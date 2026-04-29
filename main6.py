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
    ApplicationCreateRequest, ApplicationResponse, ApplicationDeleteRequest,
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


def fetch_customer_by_mobile(cur, mobile: str):
    cur.execute(
        """
        SELECT *
        FROM gold_schema.accounts
        WHERE mobile = %s
        """,
        (mobile,)
    )
    customer = cur.fetchone()
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer


def fetch_applications_for_account(cur, account_id: int):
    cur.execute(
        """
        SELECT *
        FROM gold_schema.applications
        WHERE account_id = %s
        ORDER BY created_at DESC
        """,
        (account_id,)
    )
    return cur.fetchall()


def fetch_application_ids(cur, account_id: int):
    cur.execute(
        """
        SELECT application_id
        FROM gold_schema.applications
        WHERE account_id = %s
        ORDER BY created_at DESC
        """,
        (account_id,)
    )
    return [row["application_id"] for row in cur.fetchall()]


def fetch_estimations_for_account(cur, account_id: int):
    cur.execute(
        """
        SELECT e.*, m.application_id
        FROM gold_schema.estimations e
        LEFT JOIN gold_schema.estimation_application_map m
            ON e.estimation_id = m.estimation_id
        WHERE e.account_id = %s
        ORDER BY e.estimation_date DESC, e.created_at DESC
        """,
        (account_id,)
    )
    estimations = cur.fetchall()

    estimation_ids = [est["estimation_id"] for est in estimations]
    items_by_estimation = {}
    if estimation_ids:
        cur.execute(
            """
            SELECT *
            FROM gold_schema.estimation_items
            WHERE estimation_id = ANY(%s)
            ORDER BY estimation_id, created_at ASC
            """,
            (estimation_ids,)
        )
        for item in cur.fetchall():
            items_by_estimation.setdefault(item["estimation_id"], []).append(item)

    for estimation in estimations:
        estimation["items"] = items_by_estimation.get(estimation["estimation_id"], [])

    return estimations


def fetch_invoices_for_account(cur, account_id: int):
    cur.execute(
        """
        SELECT *
        FROM gold_schema.payment_invoices
        WHERE account_id = %s
        ORDER BY created_at DESC
        """,
        (account_id,)
    )
    invoices = cur.fetchall()

    invoice_ids = [invoice["payment_invoice_id"] for invoice in invoices]
    items_by_invoice = {}
    settlements_by_invoice = {}
    if invoice_ids:
        cur.execute(
            """
            SELECT *
            FROM gold_schema.payment_invoice_items
            WHERE payment_invoice_id = ANY(%s)
            ORDER BY payment_invoice_id, created_at ASC
            """,
            (invoice_ids,)
        )
        for item in cur.fetchall():
            items_by_invoice.setdefault(item["payment_invoice_id"], []).append(item)

        cur.execute(
            """
            SELECT *
            FROM gold_schema.payment_settlements
            WHERE payment_invoice_id = ANY(%s)
            ORDER BY payment_invoice_id, payment_date DESC, created_at DESC
            """,
            (invoice_ids,)
        )
        for settlement in cur.fetchall():
            settlements_by_invoice.setdefault(settlement["payment_invoice_id"], []).append(settlement)

    for invoice in invoices:
        invoice["items"] = items_by_invoice.get(invoice["payment_invoice_id"], [])
        invoice["settlements"] = settlements_by_invoice.get(invoice["payment_invoice_id"], [])

    return invoices


def fetch_account_addresses(cur, account_id: int):
    cur.execute(
        """
        SELECT *
        FROM gold_schema.addresses
        WHERE account_id = %s
        ORDER BY created_at ASC
        """,
        (account_id,)
    )
    return cur.fetchall()


def fetch_bank_accounts(cur, account_id: int):
    cur.execute(
        """
        SELECT *
        FROM gold_schema.bank_accounts
        WHERE account_id = %s
        ORDER BY is_primary DESC, created_at ASC
        """,
        (account_id,)
    )
    return cur.fetchall()


def fetch_account_documents(cur, account_id: int):
    cur.execute(
        """
        SELECT *
        FROM gold_schema.account_documents
        WHERE account_id = %s
        ORDER BY uploaded_at DESC
        """,
        (account_id,)
    )
    return cur.fetchall()


def fetch_ornaments_for_applications(cur, application_ids):
    if not application_ids:
        return []

    cur.execute(
        """
        SELECT *
        FROM gold_schema.ornaments
        WHERE application_id = ANY(%s)
        ORDER BY application_id, created_at ASC
        """,
        (application_ids,)
    )
    return cur.fetchall()


def fetch_ornaments_for_application(cur, account_id: int, application_id: int):
    cur.execute(
        """
        SELECT a.application_id, a.application_no, a.status, a.total_quantity, a.total_weight_gms
        FROM gold_schema.applications a
        WHERE a.account_id = %s AND a.application_id = %s
        LIMIT 1
        """,
        (account_id, application_id)
    )
    application = cur.fetchone()
    if not application:
        raise HTTPException(404, "Application not found")

    cur.execute(
        """
        SELECT *
        FROM gold_schema.ornaments
        WHERE application_id = %s
        ORDER BY created_at ASC, item_id ASC
        """,
        (application_id,)
    )
    ornaments = cur.fetchall()

    total_quantity = application.get("total_quantity") if isinstance(application, dict) else application[3]
    total_weight_gms = application.get("total_weight_gms") if isinstance(application, dict) else application[4]

    return {
        "application": application,
        "ornaments": ornaments,
        "summary": {
            "count": len(ornaments),
            "total_quantity": int(total_quantity or 0),
            "total_weight_gms": float(total_weight_gms or 0)
        }
    }


def fetch_estimation_preview_context(cur, account_id: int, application_id: int):
    cur.execute(
        """
        SELECT *
        FROM gold_schema.accounts
        WHERE account_id = %s
        LIMIT 1
        """,
        (account_id,)
    )
    customer = cur.fetchone()
    if not customer:
        raise HTTPException(404, "Customer not found")

    cur.execute(
        """
        SELECT *
        FROM gold_schema.applications
        WHERE account_id = %s AND application_id = %s
        LIMIT 1
        """,
        (account_id, application_id)
    )
    application = cur.fetchone()
    if not application:
        raise HTTPException(404, "Application not found")

    cur.execute(
        """
        SELECT *
        FROM gold_schema.addresses
        WHERE account_id = %s
        ORDER BY created_at ASC
        """,
        (account_id,)
    )
    addresses = cur.fetchall()

    cur.execute(
        """
        SELECT *
        FROM gold_schema.account_documents
        WHERE account_id = %s
        ORDER BY uploaded_at DESC
        """,
        (account_id,)
    )
    documents = cur.fetchall()

    cur.execute(
        """
        SELECT *
        FROM gold_schema.pledge_details
        WHERE application_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (application_id,)
    )
    pledge_details = cur.fetchone()

    return {
        "customer": customer,
        "application": application,
        "addresses": addresses,
        "documents": documents,
        "pledge_details": pledge_details
    }


def fetch_application_preview_context(cur, account_id: int, application_id: int):
    cur.execute(
        """
        SELECT *
        FROM gold_schema.accounts
        WHERE account_id = %s
        LIMIT 1
        """,
        (account_id,)
    )
    customer = cur.fetchone()
    if not customer:
        raise HTTPException(404, "Customer not found")

    cur.execute(
        """
        SELECT *
        FROM gold_schema.applications
        WHERE account_id = %s AND application_id = %s
        LIMIT 1
        """,
        (account_id, application_id)
    )
    application = cur.fetchone()
    if not application:
        raise HTTPException(404, "Application not found")

    addresses = fetch_account_addresses(cur, account_id)

    cur.execute(
        """
        SELECT document_type, file_path, uploaded_at
        FROM gold_schema.account_documents
        WHERE account_id = %s
          AND document_type ILIKE '%%photo%%'
        ORDER BY uploaded_at DESC
        """,
        (account_id,)
    )
    documents = cur.fetchall()

    cur.execute(
        """
        SELECT *
        FROM gold_schema.pledge_details
        WHERE application_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (application_id,)
    )
    pledge_details = cur.fetchone()

    cur.execute(
        """
        SELECT *
        FROM gold_schema.ornaments
        WHERE application_id = %s
        ORDER BY created_at ASC, item_id ASC
        """,
        (application_id,)
    )
    ornaments = cur.fetchall()

    return {
        "customer": customer,
        "application": application,
        "addresses": addresses,
        "documents": documents,
        "pledge_details": pledge_details,
        "ornaments": ornaments
    }


def fetch_pledge_details_for_applications(cur, application_ids):
    if not application_ids:
        return []

    cur.execute(
        """
        SELECT *
        FROM gold_schema.pledge_details
        WHERE application_id = ANY(%s)
        ORDER BY application_id, created_at DESC
        """,
        (application_ids,)
    )
    return cur.fetchall()


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

# @app.post("/accounts/addresses")
# def add_address(mobile: str, payload: AddressCreateRequest):
#     conn = get_connection()
#     cur = conn.cursor()
#     try:
#         account_id = get_account_id(cur, mobile)
#         cur.execute(
#             """
#             INSERT INTO gold_schema.addresses (
#                 account_id, address_type,
#                 address_line, street,
#                 city, state, country, pincode
#             )
#             VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
#             """,
#             (
#                 account_id,
#                 payload.address_type,
#                 payload.address_line,
#                 payload.street,
#                 payload.city,
#                 payload.state,
#                 payload.country,
#                 payload.pincode
#             )
#         )
#         conn.commit()
#         return {"status": "ADDRESS_SAVED"}
#     finally:
#         cur.close()
#         conn.close()

@app.post("/accounts/addresses")
def add_address(mobile: str, payload: AddressCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        
        # Check if address already exists
        cur.execute(
            """
            SELECT 1 FROM gold_schema.addresses
            WHERE account_id = %s AND address_type = %s
            """,
            (account_id, payload.address_type)
        )
        exists = cur.fetchone()
        
        if exists:
            # Update existing address
            cur.execute(
                """
                UPDATE gold_schema.addresses
                SET address_line = %s,
                    street = %s,
                    city = %s,
                    state = %s,
                    country = %s,
                    pincode = %s
                WHERE account_id = %s AND address_type = %s
                """,
                (
                    payload.address_line,
                    payload.street,
                    payload.city,
                    payload.state,
                    payload.country,
                    payload.pincode,
                    account_id,
                    payload.address_type
                )
            )
        else:
            # Insert new address
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
        
        # Check if bank account already exists
        cur.execute(
            """
            SELECT 1 FROM gold_schema.bank_accounts
            WHERE account_id = %s AND account_number = %s
            """,
            (account_id, payload.account_number)
        )
        exists = cur.fetchone()
        
        if exists:
            # Update existing bank account
            if payload.is_primary:
                cur.execute(
                    """
                    UPDATE gold_schema.bank_accounts
                    SET is_primary = FALSE
                    WHERE account_id = %s
                    """,
                    (account_id,)
                )
            cur.execute(
                """
                UPDATE gold_schema.bank_accounts
                SET bank_name = %s,
                    branch = %s,
                    ifsc_code = %s,
                    account_holder_name = %s,
                    account_holder_type = %s,
                    is_primary = %s
                WHERE account_id = %s AND account_number = %s
                """,
                (
                    payload.bank_name,
                    payload.branch,
                    payload.ifsc_code,
                    payload.account_holder_name,
                    payload.account_holder_type,
                    payload.is_primary,
                    account_id,
                    payload.account_number
                )
            )
        else:
            # Insert new bank account
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
        
        # Validate required fields
        if not payload.document_type or not payload.document_type.strip():
            raise HTTPException(400, 'document_type is required')
        
        if payload.document_type.upper() != 'OTHER':
            if not payload.file_path or not payload.file_path.strip():
                raise HTTPException(400, f'file_path is required for {payload.document_type} documents')
            if not payload.file_name or not payload.file_name.strip():
                raise HTTPException(400, f'file_name is required for {payload.document_type} documents')

        # Check if a document of this type already exists for the account
        cur.execute(
            """
            SELECT document_id FROM gold_schema.account_documents
            WHERE account_id = %s AND document_type = %s
            """,
            (account_id, payload.document_type)
        )
        existing = cur.fetchone()

        if existing:
            # Update existing document
            cur.execute(
                """
                UPDATE gold_schema.account_documents
                SET document_number = %s,
                    file_path = %s,
                    file_name = %s,
                    file_size_mb = %s,
                    uploaded_at = CURRENT_TIMESTAMP
                WHERE document_id = %s
                """,
                (
                    payload.document_number,
                    payload.file_path,
                    payload.file_name,
                    payload.file_size_mb,
                    existing[0]
                )
            )
        else:
            # Insert new document
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
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f'Error saving document: {str(e)}')
    finally:
        cur.close()
        conn.close()


@app.delete("/accounts/documents")
def delete_document(mobile: str, document_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            DELETE FROM gold_schema.account_documents
            WHERE account_id = %s AND document_id = %s
            RETURNING document_id
            """,
            (account_id, document_id)
        )
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(404, "Document not found")
        conn.commit()
        return {"status": "DOCUMENT_DELETED"}
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

        # Check if application exists
        cur.execute(
            """
            SELECT application_id, status FROM gold_schema.applications
            WHERE account_id = %s AND application_no = %s
            """,
            (account_id, application_no)
        )
        existing = cur.fetchone()

        if existing:
            application_id, status = existing
            if status != 'DRAFT':
                raise HTTPException(409, "Active application already exists")
            # Update existing draft application
            cur.execute(
                """
                UPDATE gold_schema.applications
                SET application_type = %s,
                    application_date = %s,
                    place = %s
                WHERE application_id = %s
                """,
                (
                    payload.application_type,
                    payload.application_date,
                    payload.place,
                    application_id
                )
            )
            app_id, app_no, status = application_id, application_no, 'DRAFT'
        else:
            # Create new application
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


@app.delete("/applications/delete")
def delete_application(payload: ApplicationDeleteRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)
        
        # Check if application exists and belongs to user
        cur.execute(
            """
            SELECT status FROM gold_schema.applications
            WHERE application_id = %s AND account_id = %s
            """,
            (payload.application_id, account_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Application not found")
        
        status = row[0]
        if status != 'DRAFT':
            raise HTTPException(400, "Only draft applications can be deleted")
        
        # Delete the application (cascade will handle related records)
        cur.execute(
            "DELETE FROM gold_schema.applications WHERE application_id = %s",
            (payload.application_id,)
        )
        
        conn.commit()
        return {"message": "Application deleted successfully"}
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

# @app.post("/applications/pledge-details", response_model=PledgeDetailsResponse)
# def create_pledge_details(payload: PledgeDetailsCreateRequest):
#     conn = get_connection()
#     cur = conn.cursor()
#     try:
#         account_id = get_account_id(cur, payload.mobile)

#         cur.execute(
#             "SELECT first_name, last_name FROM gold_schema.accounts WHERE account_id = %s",
#             (account_id,)
#         )
#         row = cur.fetchone()
#         if not row:
#             raise HTTPException(404, "Account missing for pledge details")

#         pledger_name = f"{row[0]} {row[1]}".strip()
#         pledger_address = payload.pledger_address.strip() if payload.pledger_address else ""

#         if not pledger_address:
#             raise HTTPException(400, "pledger_address is required")

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

        if not getattr(payload, 'application_id', None):
            raise HTTPException(400, "application_id is required for pledge details")

        cur.execute(
            """
            SELECT application_id
            FROM gold_schema.applications
            WHERE account_id = %s
              AND application_id = %s
              AND application_type = 'PLEDGE_RELEASE'
              AND status IN ('DRAFT', 'SUBMITTED', 'APPROVED')
            LIMIT 1
            """,
            (account_id, payload.application_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(409, "No matching PLEDGE_RELEASE application found")

        application_id = row[0]

        cur.execute(
            "SELECT pledge_id FROM gold_schema.pledge_details WHERE application_id=%s",
            (application_id,)
        )
        existing_pledge = cur.fetchone()
        
        if existing_pledge:
            # Update existing pledge details
            pledge_id = existing_pledge[0]
            cur.execute(
                """
                UPDATE gold_schema.pledge_details
                SET pledger_name=%s,
                    pledger_address=%s,
                    financier_name=%s,
                    branch_name=%s,
                    gold_loan_account_no=%s,
                    principal_amount=%s,
                    interest_amount=%s,
                    total_due=%s
                WHERE pledge_id=%s
                """,
                (
                    pledger_name,
                    pledger_address,
                    payload.financier_name,
                    payload.branch_name,
                    payload.gold_loan_account_no,
                    payload.principal_amount,
                    payload.interest_amount,
                    payload.principal_amount + (payload.interest_amount or 0),
                    pledge_id
                )
            )
        else:
            # Insert new pledge details
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
              AND application_id=%s
              AND status IN ('DRAFT','SUBMITTED','APPROVED')
            LIMIT 1
            """,
            (account_id, payload.application_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(409, "No active application")

        application_id, application_no, status = row

        for item in payload.ornaments:
            if getattr(item, 'item_id', None):
                cur.execute(
                    """
                    SELECT 1
                    FROM gold_schema.ornaments
                    WHERE application_id = %s
                      AND item_id = %s
                    LIMIT 1
                    """,
                    (application_id, item.item_id)
                )
                if cur.fetchone():
                    cur.execute(
                        """
                        UPDATE gold_schema.ornaments
                        SET item_name = %s,
                            quantity = %s,
                            purity_percentage = %s,
                            approx_weight_gms = %s,
                            item_photo_url = %s
                        WHERE item_id = %s
                        """,
                        (
                            item.item_name,
                            item.quantity,
                            item.purity_percentage,
                            item.approx_weight_gms,
                            item.item_photo_url,
                            item.item_id
                        )
                    )
                    continue

            cur.execute(
                """
                SELECT item_id
                FROM gold_schema.ornaments
                WHERE application_id = %s
                  AND item_name = %s
                  AND purity_percentage = %s
                  AND approx_weight_gms = %s
                  AND item_photo_url = %s
                LIMIT 1
                """,
                (
                    application_id,
                    item.item_name,
                    item.purity_percentage,
                    item.approx_weight_gms,
                    item.item_photo_url
                )
            )
            existing = cur.fetchone()

            if existing:
                cur.execute(
                    """
                    UPDATE gold_schema.ornaments
                    SET quantity = %s
                    WHERE item_id = %s
                    """,
                    (
                        item.quantity,
                        existing[0]
                    )
                )
            else:
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

        cur.execute(
            """
            SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(approx_weight_gms), 0)
            FROM gold_schema.ornaments
            WHERE application_id = %s
            """,
            (application_id,)
        )
        total_qty, total_wt = cur.fetchone()

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


@app.get("/applications/ornaments/by-application")
def get_ornaments_by_application(
    mobile: str = Query(...),
    application_id: int = Query(...)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        account_id = get_account_id(cur, mobile)
        return fetch_ornaments_for_application(cur, account_id, application_id)
    finally:
        cur.close()
        conn.close()


@app.get("/applications/estimation-preview")
def get_estimation_preview(
    mobile: str = Query(...),
    application_id: int = Query(...)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        account_id = get_account_id(cur, mobile)
        return fetch_estimation_preview_context(cur, account_id, application_id)
    finally:
        cur.close()
        conn.close()


@app.get("/applications/application-preview")
def get_application_preview(
    mobile: str = Query(...),
    application_id: int = Query(...)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        account_id = get_account_id(cur, mobile)
        return fetch_application_preview_context(cur, account_id, application_id)
    finally:
        cur.close()
        conn.close()


@app.delete("/applications/ornaments/{item_id}")
def delete_ornament(item_id: int, mobile: str = Query(...)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)

        cur.execute(
            """
            SELECT o.application_id
            FROM gold_schema.ornaments o
            JOIN gold_schema.applications a ON o.application_id = a.application_id
            WHERE o.item_id = %s AND a.account_id = %s
            LIMIT 1
            """,
            (item_id, account_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ornament not found")

        application_id = row[0]

        cur.execute(
            "SELECT status FROM gold_schema.applications WHERE application_id = %s",
            (application_id,)
        )
        app_row = cur.fetchone()
        if not app_row or app_row[0] != 'DRAFT':
            raise HTTPException(400, "Only ornaments in DRAFT applications can be deleted")

        cur.execute("DELETE FROM gold_schema.ornaments WHERE item_id = %s", (item_id,))

        cur.execute(
            """
            SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(approx_weight_gms), 0)
            FROM gold_schema.ornaments
            WHERE application_id = %s
            """,
            (application_id,)
        )
        total_qty, total_wt = cur.fetchone()

        cur.execute(
            """
            UPDATE gold_schema.applications
            SET total_quantity=%s, total_weight_gms=%s
            WHERE application_id=%s
            """,
            (total_qty, round(total_wt, 3), application_id)
        )

        conn.commit()
        return {"status": "deleted", "item_id": item_id}
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

            estimation_net_weight += float(calc["net_gold_weight"])
            estimation_gross_amount += float(calc["gross_amount"])
            estimation_net_amount += float(calc["net_amount"])

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
            "net_weight_gms": round(estimation_net_weight, 2),
            "gross_amount": round(estimation_gross_amount, 2),
            "net_amount": round(estimation_net_amount, 2),
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

        cur.execute(
            "SELECT payment_invoice_id, payment_status FROM gold_schema.payment_invoices WHERE account_id=%s AND invoice_no=%s LIMIT 1",
            (account_id, payload.invoice_no)
        )
        existing_invoice = cur.fetchone()

        if existing_invoice:
            return {
                "payment_invoice_id": existing_invoice[0],
                "invoice_no": payload.invoice_no,
                "payment_status": existing_invoice[1]
            }

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

        cur.execute("SELECT COALESCE(SUM(net_amount),0) FROM gold_schema.estimation_items WHERE estimation_id=%s", (estimation_id,))
        #payload_total = cur.fetchone()[0]

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
            payload.total_net_amount,
            #payload_total,
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

        if payload.deduction_percentage < 0 or payload.deduction_percentage > 100:
            raise HTTPException(400, "deduction_percentage must be a percentage between 0 and 100")

        cur.execute("""
            SELECT invoice_item_id
            FROM gold_schema.payment_invoice_items
            WHERE payment_invoice_id = %s
              AND item_name = %s
              AND weight_before_melting = %s
              AND weight_after_melting = %s
              AND purity_after_melting = %s
              AND gold_rate_per_gm = %s
              AND gross_amount = %s
              AND deduction_percentage = %s
              AND net_amount = %s
            LIMIT 1
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
        existing_item = cur.fetchone()

        if existing_item:
            item_id = existing_item[0]
        else:
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
            SELECT settlement_id
            FROM gold_schema.payment_settlements
            WHERE payment_invoice_id = %s
              AND payment_mode = %s
              AND paid_amount = %s
              AND payment_date = %s
            LIMIT 1
        """, (
            invoice_id,
            payload.payment_mode,
            payload.paid_amount,
            payload.payment_date
        ))
        existing_settlement = cur.fetchone()

        if existing_settlement:
            settlement_id = existing_settlement[0]
        else:
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



@app.get("/branches")
def get_branches():
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT branch_code, branch_name, full_address_txt, phone_number FROM gold_schema.branches")
        rows = cur.fetchall()
        branches = [
            {
                "branch_code": row[0],
                "branch_name": row[1],
                "full_address_txt": row[2],
                "phone_number": row[3]
            }
            for row in rows
        ]
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


# @app.get("/customers/search")
# def search_customer(mobile: str = Query(...)):
#     conn = get_connection()
#     cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
#     try:
#         cur.execute("SELECT * FROM gold_schema.accounts WHERE mobile=%s", (mobile,))
#         customer = cur.fetchone()
#         if not customer:
#             raise HTTPException(404, "Customer not found")

#         account_id = customer['account_id']

#         # Fetch all applications
#         cur.execute("SELECT * FROM gold_schema.applications WHERE account_id=%s ORDER BY created_at DESC", (account_id,))
#         applications = cur.fetchall()

#         # Fetch all estimations with items
#         cur.execute("""
#             SELECT e.*, m.application_id
#             FROM gold_schema.estimations e
#             JOIN gold_schema.estimation_application_map m ON e.estimation_id=m.estimation_id
#             WHERE e.account_id=%s ORDER BY e.estimation_date DESC
#         """, (account_id,))
#         estimations = cur.fetchall()
#         for est in estimations:
#             cur.execute("SELECT * FROM gold_schema.estimation_items WHERE estimation_id=%s", (est['estimation_id'],))
#             est['items'] = cur.fetchall()

#         # Fetch all invoices with items and settlements
#         cur.execute("SELECT * FROM gold_schema.payment_invoices WHERE account_id=%s ORDER BY created_at DESC", (account_id,))
#         invoices = cur.fetchall()
#         for inv in invoices:
#             invoice_id = inv['payment_invoice_id']
#             cur.execute("SELECT * FROM gold_schema.payment_invoice_items WHERE payment_invoice_id=%s", (invoice_id,))
#             inv['items'] = cur.fetchall()
#             cur.execute("SELECT * FROM gold_schema.payment_settlements WHERE payment_invoice_id=%s ORDER BY payment_date DESC", (invoice_id,))
#             inv['settlements'] = cur.fetchall()

#         # Fetch all addresses
#         cur.execute("SELECT * FROM gold_schema.addresses WHERE account_id=%s", (account_id,))
#         addresses = cur.fetchall()

#         # Fetch all bank accounts
#         cur.execute("SELECT * FROM gold_schema.bank_accounts WHERE account_id=%s", (account_id,))
#         bank_accounts = cur.fetchall()

#         # Fetch all documents
#         cur.execute("SELECT * FROM gold_schema.account_documents WHERE account_id=%s", (account_id,))
#         documents = cur.fetchall()

#         return {
#             "customer": customer,
#             "applications": applications,
#             "estimations": estimations,
#             "invoices": invoices,
#             "addresses": addresses,
#             "bank_accounts": bank_accounts,
#             "documents": documents
#         }
#     finally:
#         cur.close()
#         conn.close()
@app.get("/customers/search")
def search_customer(mobile: str = Query(...)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        customer = fetch_customer_by_mobile(cur, mobile)
        account_id = customer["account_id"]
        applications = fetch_applications_for_account(cur, account_id)
        application_ids = [app["application_id"] for app in applications]

        return {
            "customer": customer,
            "applications": applications,
            "estimations": fetch_estimations_for_account(cur, account_id),
            "invoices": fetch_invoices_for_account(cur, account_id),
            "addresses": fetch_account_addresses(cur, account_id),
            "bank_accounts": fetch_bank_accounts(cur, account_id),
            "documents": fetch_account_documents(cur, account_id),
            "ornaments": fetch_ornaments_for_applications(cur, application_ids),
            "pledge_details": fetch_pledge_details_for_applications(cur, application_ids)
        }
    finally:
        cur.close()
        conn.close()


@app.get("/customers/summary")
def get_customer_summary(
    mobile: str = Query(...),
    include: str = Query("customer", description="Comma-separated list of data to include: customer,applications,estimations,invoices,addresses,bank_accounts,documents,ornaments,pledge_details")
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        customer = fetch_customer_by_mobile(cur, mobile)
        account_id = customer["account_id"]
        result = {"customer": customer}

        include_list = [item.strip() for item in include.split(',') if item.strip()]
        include_set = set(include_list)
        application_ids = None

        if "applications" in include_set:
            applications = fetch_applications_for_account(cur, account_id)
            result["applications"] = applications
            application_ids = [app["application_id"] for app in applications]

        if "estimations" in include_set:
            result["estimations"] = fetch_estimations_for_account(cur, account_id)

        if "invoices" in include_set:
            result["invoices"] = fetch_invoices_for_account(cur, account_id)

        if "addresses" in include_set:
            result["addresses"] = fetch_account_addresses(cur, account_id)

        if "bank_accounts" in include_set:
            result["bank_accounts"] = fetch_bank_accounts(cur, account_id)

        if "documents" in include_set:
            result["documents"] = fetch_account_documents(cur, account_id)

        if "ornaments" in include_set or "pledge_details" in include_set:
            if application_ids is None:
                application_ids = fetch_application_ids(cur, account_id)

            if "ornaments" in include_set:
                result["ornaments"] = fetch_ornaments_for_applications(cur, application_ids)

            if "pledge_details" in include_set:
                result["pledge_details"] = fetch_pledge_details_for_applications(cur, application_ids)

        return result
    finally:
        cur.close()
        conn.close()


# @app.get("/transactions/all")
# def get_transactions(
#     mobile: str = Query(None),
#     start_date: date = Query(None),
#     end_date: date = Query(None),
#     days: int = Query(None)
# ):
#     conn = get_connection()
#     cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
#     try:
#         account_condition = ""
#         params = []

#         if mobile:
#             account_id = get_account_id(cur, mobile)
#             account_condition = "AND account_id = %s"
#             params.append(account_id)

#         if days is not None:
#             end_date = date.today()
#             start_date = date.today() - timedelta(days=days)

#         if start_date is not None and end_date is not None:
#             account_condition += " AND invoice_date BETWEEN %s AND %s"
#             params.extend([start_date, end_date])

#         invoices_sql = f"SELECT * FROM gold_schema.payment_invoices WHERE 1=1 {account_condition} ORDER BY invoice_date DESC"
#         cur.execute(invoices_sql, tuple(params))
#         invoices = cur.fetchall()

#         invoice_ids = [r['payment_invoice_id'] for r in invoices]

#         item_params = []
#         settlements_params = []
#         cond_items = ""
#         cond_settlements = ""

#         if invoice_ids:
#             cond_items = "WHERE payment_invoice_id = ANY(%s)"
#             item_params = [invoice_ids]
#             cond_settlements = "WHERE payment_invoice_id = ANY(%s)"
#             settlements_params = [invoice_ids]

#         cur.execute(f"SELECT * FROM gold_schema.payment_invoice_items {cond_items}", tuple(item_params))
#         items = cur.fetchall()

#         cur.execute(f"SELECT * FROM gold_schema.payment_settlements {cond_settlements} ORDER BY payment_date DESC", tuple(settlements_params))
#         settlements = cur.fetchall()

#         total_invoice_amount = sum(float(r.get('total_net_amount') or 0) for r in invoices)
#         total_settled_amount = sum(float(r.get('paid_amount') or 0) for r in settlements)

#         return {
#             "invoices": invoices,
#             "invoice_items": items,
#             "settlements": settlements,
#             "summary": {
#                 "total_invoices": len(invoices),
#                 "total_invoice_amount": total_invoice_amount,
#                 "total_settled_amount": total_settled_amount
#             }
#         }
#     finally:
#         cur.close()
#         conn.close()

@app.get("/transactions/all")
def get_transactions(
    mobile: str = Query(None),
    start_date: date = Query(None),
    end_date: date = Query(None),
    days: int = Query(None)
):
    """
    Enhanced transactions endpoint with customer details
    Fixed version - no SQL ambiguous column references
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Build WHERE conditions and parameters
        where_conditions = ["1=1"]
        params = []

        if mobile:
            account_id = get_account_id(cur, mobile)
            where_conditions.append("pi.account_id = %s")
            params.append(account_id)

        if days is not None:
            end_date = date.today()
            start_date = date.today() - timedelta(days=days)

        if start_date is not None and end_date is not None:
            where_conditions.append("pi.invoice_date BETWEEN %s AND %s")
            params.extend([start_date, end_date])

        where_clause = " AND ".join(where_conditions)

        # Enhanced invoices query - FIXED with proper column aliases
        invoices_query = f"""
            SELECT 
                pi.payment_invoice_id,
                pi.account_id as invoice_account_id,
                pi.application_id,
                pi.estimation_id,
                pi.invoice_no,
                pi.invoice_date,
                pi.total_net_amount,
                pi.amount_in_words,
                pi.payment_status,
                pi.remarks,
                pi.created_at,
                a.account_id,
                a.first_name,
                a.last_name,
                a.mobile as customer_mobile,
                a.phone as customer_phone,
                a.email as customer_email
            FROM gold_schema.payment_invoices pi
            LEFT JOIN gold_schema.accounts a ON pi.account_id = a.account_id
            WHERE {where_clause}
            ORDER BY pi.invoice_date DESC
        """
        
        cur.execute(invoices_query, tuple(params))
        invoices = cur.fetchall()

        # Fetch customer details for each invoice
        for invoice in invoices:
            if invoice.get('account_id'):
                customer_details = {
                    "account_id": invoice.get('account_id'),
                    "first_name": invoice.get('first_name', 'Unknown'),
                    "last_name": invoice.get('last_name', 'Unknown'),
                    "mobile": invoice.get('customer_mobile', 'Unknown'),
                    "phone": invoice.get('customer_phone'),
                    "email": invoice.get('customer_email')
                }
                invoice['customer_details'] = customer_details
                invoice['customer_name'] = f"{customer_details.get('first_name', 'Unknown')} {customer_details.get('last_name', 'Unknown')}"

        # Get invoice IDs for related data
        invoice_ids = [r['payment_invoice_id'] for r in invoices]

        # Fetch invoice items
        items = []
        if invoice_ids:
            items_query = """
                SELECT * FROM gold_schema.payment_invoice_items 
                WHERE payment_invoice_id = ANY(%s)
            """
            cur.execute(items_query, (invoice_ids,))
            items = cur.fetchall()

        # Fetch settlements with customer details - FIXED
        settlements = []
        if invoice_ids:
            settlements_query = """
                SELECT 
                    ps.settlement_id,
                    ps.payment_invoice_id,
                    ps.payment_mode,
                    ps.paid_amount,
                    ps.payment_date,
                    ps.reference_no,
                    ps.created_at,
                    a.account_id as settlement_account_id,
                    a.first_name as settlement_first_name,
                    a.last_name as settlement_last_name,
                    a.mobile as settlement_mobile,
                    a.phone as settlement_phone,
                    a.email as settlement_email
                FROM gold_schema.payment_settlements ps
                LEFT JOIN gold_schema.payment_invoices pi ON ps.payment_invoice_id = pi.payment_invoice_id
                LEFT JOIN gold_schema.accounts a ON pi.account_id = a.account_id
                WHERE ps.payment_invoice_id = ANY(%s)
                ORDER BY ps.payment_date DESC
            """
            cur.execute(settlements_query, (invoice_ids,))
            settlements = cur.fetchall()

            # Add customer details to settlements
            for settlement in settlements:
                if settlement.get('settlement_account_id'):
                    customer_details = {
                        "account_id": settlement.get('settlement_account_id'),
                        "first_name": settlement.get('settlement_first_name', 'Unknown'),
                        "last_name": settlement.get('settlement_last_name', 'Unknown'),
                        "mobile": settlement.get('settlement_mobile', 'Unknown'),
                        "phone": settlement.get('settlement_phone'),
                        "email": settlement.get('settlement_email')
                    }
                    settlement['customer_details'] = customer_details
                    settlement['customer_name'] = f"{customer_details.get('first_name', 'Unknown')} {customer_details.get('last_name', 'Unknown')}"

        # Calculate totals
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
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch transactions: {str(e)}")
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
