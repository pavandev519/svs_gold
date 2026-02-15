from fastapi import FastAPI, HTTPException, Query
import psycopg2
import psycopg2.extras
from db import get_connection
from models4 import (
    AccountCheckRequest, AccountCheckResponse,
    AccountCreateRequest, AccountCreateResponse,
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
    return row[0]


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
                first_name, last_name, contact_person,
                mobile, phone, email,
                gender, date_of_birth, aadhar_no,
                yearly_income, occupation,
                gst_no, pan_no,
                source, owner,
                state, district, city, pincode,
                address_text
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING account_id, account_code
            """,
            (
                payload.account_type,
                payload.account_code,
                payload.first_name,
                payload.last_name,
                payload.contact_person,
                payload.mobile,
                payload.phone,
                payload.email,
                payload.gender,
                payload.date_of_birth,
                payload.aadhar_no,
                payload.yearly_income,
                payload.occupation,
                payload.gst_no,
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
            AND status IN ('SUBMITTED','APPROVED')
            AND application_no = %s
            """,
            (account_id,application_no)
        )
        if cur.fetchone():
            raise HTTPException(409, "Active application already exists")

        cur.execute(
            """
            INSERT INTO gold_schema.applications (
                account_id, application_type,
                application_date, application_no,
                place, status
            )
            VALUES (%s,%s,%s,%s,%s,'SUBMITTED')
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
                    place=r[4],
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

@app.post("/applications/pledge-details", response_model=PledgeDetailsResponse)
def create_pledge_details(payload: PledgeDetailsCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)

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
                authorized_person, principal_amount,
                interest_amount, total_due,
                cheque_no, cheque_date,
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
            AND status IN ('SUBMITTED','APPROVED')
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
            AND status IN ('SUBMITTED','APPROVED')
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
            "net_weight_gms": calc["net_gold_weight"],
            "gross_amount": calc["gross_amount"],
            "net_amount": calc["net_amount"],
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

        cur.execute("""
            INSERT INTO gold_schema.payment_invoice_items (
                payment_invoice_id,
                item_name,
                weight_before_melting,
                weight_after_melting,
                purity_after_melting,
                gold_rate_per_gm,
                gross_amount,
                deductions_amount,
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
            payload.deductions_amount,
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


@app.post("/payments/deduction", response_model=PaymentDeductionResponse)
def add_deduction(payload: PaymentDeductionCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO gold_schema.payment_deductions (
                invoice_item_id,
                deduction_type,
                deduction_amount
            )
            VALUES (%s,%s,%s)
            RETURNING deduction_id
        """, (
            payload.invoice_item_id,
            payload.deduction_type,
            payload.deduction_amount
        ))

        deduction_id = cur.fetchone()[0]
        conn.commit()

        return {
            "deduction_id": deduction_id,
            "invoice_item_id": payload.invoice_item_id
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
            INSERT INTO gold_schema.payment_settlements (
                payment_invoice_id,
                payment_mode,
                paid_amount,
                reference_no,
                bank_name,
                payment_date
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING settlement_id
        """, (
            invoice_id,
            payload.payment_mode,
            payload.paid_amount,
            payload.reference_no,
            payload.bank_name,
            payload.payment_date
        ))

        settlement_id = cur.fetchone()[0]
        conn.commit()

        return {
            "settlement_id": settlement_id,
            "payment_invoice_id": invoice_id,
            "paid_amount": payload.paid_amount
        }

    finally:
        cur.close()
        conn.close()


