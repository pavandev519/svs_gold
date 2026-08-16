from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from datetime import date, timedelta
from typing import Optional
from db import get_connection
import time
import threading
import base64
import io
from fastapi.responses import StreamingResponse
import binascii


def _normalize_blob(file_path):
    """Return raw bytes for a stored `file_path` value.

    Handles three common storage formats:
    - actual Postgres bytea / Python bytes -> return as-is
    - base64-encoded string -> decode and return bytes
    - raw text (fallback) -> return utf-8 bytes
    """
    if file_path is None:
        return None
    # bytes stored directly
    if isinstance(file_path, (bytes, bytearray)):
        return bytes(file_path)

    # strip data URL prefix if present
    if isinstance(file_path, str):
        s = file_path.strip()
        if s.startswith('data:'):
            # split at comma
            parts = s.split(',', 1)
            if len(parts) == 2:
                s = parts[1]

        # try strict base64 decode first
        try:
            decoded = base64.b64decode(s, validate=True)
            return decoded
        except (binascii.Error, ValueError):
            # not valid base64; many rows were stored as raw binary in a TEXT column
            # decode using latin-1 to map bytes 1:1 from characters
            try:
                b = s.encode('latin-1')
                return b
            except Exception:
                try:
                    return s.encode('utf-8')
                except Exception:
                    return None

    # unknown type
    return None

# Simple in-memory TTL cache for customer summaries to reduce repeated load
_SUMMARY_CACHE = {}
_SUMMARY_CACHE_LOCK = threading.Lock()
_SUMMARY_CACHE_TTL = 30.0  # seconds
# Per-application ornaments summary cache
_ORNAMENT_SUMMARY_CACHE = {}
_ORNAMENT_SUMMARY_CACHE_LOCK = threading.Lock()
_ORNAMENT_SUMMARY_CACHE_TTL = 60.0  # seconds


def invalidate_ornament_summary_cache(app_ids):
    """Invalidate cached ornament summaries for any cache entries that include the given app_ids."""
    if not app_ids:
        return
    try:
        ids = set(int(x) for x in app_ids)
    except Exception:
        ids = set(app_ids)
    with _ORNAMENT_SUMMARY_CACHE_LOCK:
        keys_to_delete = [k for k in _ORNAMENT_SUMMARY_CACHE.keys() if ids.intersection(set(k))]
        for k in keys_to_delete:
            _ORNAMENT_SUMMARY_CACHE.pop(k, None)
from models5 import (
    AccountCheckRequest, AccountCheckResponse,
    AccountCreateRequest, AccountCreateResponse,
    AccountUpdateRequest,
    ApplicationCreateRequest, ApplicationResponse, ApplicationUpdateRequest, ApplicationDeleteRequest,
    ApplicationListItem, ApplicationListResponse,
    OrnamentCreateRequest, OrnamentCreateResponse,
    EstimationItemCreateRequest, EstimationResponse,
    EnquiryCreateRequest, EnquiryCreateResponse, EnquiryItem, EnquiryListResponse, EnquiryUpdateRequest,
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
    PaymentSettlementResponse,
    CalcEntryCreateRequest, CalcEntryUpdateRequest, CalcEntryResponse, CalcEntryListResponse
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
    # return only metadata and limit the number of rows to avoid fetching large blobs
    cur.execute(
        """
        SELECT document_id, document_type, file_name, file_size_mb, uploaded_at
        FROM gold_schema.account_documents_meta
        WHERE account_id = %s
        ORDER BY uploaded_at DESC
        LIMIT 50
        """,
        (account_id,)
    )
    return cur.fetchall()


def fetch_ornaments_for_applications(cur, application_ids, limit: int | None = None):
    """Fetch ornaments for a list of application_ids.

    Optional `limit` caps the total rows returned to avoid heavy scans when used
    in summary endpoints. Pass a small limit (e.g. 200) from `get_customer_summary`.
    """
    if not application_ids:
        return []

    # select only required ornament columns to reduce IO and allow index-only scans
    if limit is not None:
        cur.execute(
            """
            SELECT application_id, item_id, item_name, purity_percentage, approx_weight_gms,
                   item_photo_url, quantity, created_at
            FROM gold_schema.ornaments
            WHERE application_id = ANY(%s)
            ORDER BY application_id, created_at ASC
            LIMIT %s
            """,
            (application_ids, limit)
        )
    else:
        cur.execute(
            """
            SELECT application_id, item_id, item_name, purity_percentage, approx_weight_gms,
                   item_photo_url, quantity, created_at
            FROM gold_schema.ornaments
            WHERE application_id = ANY(%s)
            ORDER BY application_id, created_at ASC
            """,
            (application_ids,)
        )
    return cur.fetchall()


def fetch_ornament_summaries_for_applications(cur, application_ids):
    """Return lightweight summaries for ornaments grouped by application.

    Each summary contains application_id, count, total_quantity and total_weight.
    This is intended for use in customer summaries to avoid scanning many rows.
    """
    if not application_ids:
        return []

    # normalize key (order-independent) and check in-memory TTL cache first
    try:
        key = tuple(sorted(int(x) for x in application_ids))
    except Exception:
        key = tuple(application_ids)

    now = time.time()
    with _ORNAMENT_SUMMARY_CACHE_LOCK:
        cached = _ORNAMENT_SUMMARY_CACHE.get(key)
        if cached and now - cached[0] < _ORNAMENT_SUMMARY_CACHE_TTL:
            return cached[1]

    cur.execute(
        """
        SELECT application_id,
               COUNT(*) AS ornament_count,
               COALESCE(SUM(quantity), 0) AS total_quantity,
               COALESCE(SUM(approx_weight_gms), 0) AS total_weight_gms
        FROM gold_schema.ornaments
        WHERE application_id = ANY(%s)
        GROUP BY application_id
        """,
        (application_ids,)
    )
    rows = cur.fetchall()
    # Normalize to list of dicts for easier consumption by callers
    summaries = []
    for r in rows:
        if isinstance(r, dict):
            summaries.append({
                "application_id": r.get("application_id"),
                "count": int(r.get("ornament_count") or 0),
                "total_quantity": int(r.get("total_quantity") or 0),
                "total_weight_gms": float(r.get("total_weight_gms") or 0.0)
            })
        else:
            summaries.append({
                "application_id": r[0],
                "count": int(r[1] or 0),
                "total_quantity": int(r[2] or 0),
                "total_weight_gms": float(r[3] or 0.0)
            })
    return summaries


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
         SELECT application_id, item_id, item_name, purity_percentage, approx_weight_gms,
             item_photo_url, quantity, created_at
        FROM gold_schema.ornaments
        WHERE application_id = %s
        ORDER BY created_at ASC, item_id ASC
        """,
        (application_id,)
    )
    ornaments = cur.fetchall()

    # If `item_photo_url` holds a document_id reference, batch-load blobs to avoid per-row queries
    try:
        # collect numeric document ids referenced
        doc_ids = []
        for o in ornaments:
            if isinstance(o, dict):
                photo_ref = o.get('item_photo_url')
            else:
                photo_ref = o[5] if len(o) > 5 else None
            try:
                did = int(photo_ref)
            except Exception:
                did = None
            if did:
                doc_ids.append(did)

        if doc_ids:
            # fetch blobs for all referenced doc ids in one query (owner check)
            cur.execute(
                """
                SELECT document_id, file_path
                FROM gold_schema.account_documents
                WHERE document_id = ANY(%s) AND account_id = %s
                """,
                (list(set(doc_ids)), account_id)
            )
            rows = cur.fetchall()
            blob_map = {}
            for r in rows:
                if isinstance(r, dict):
                    blob_map[int(r.get('document_id'))] = r.get('file_path')
                else:
                    blob_map[int(r[0])] = r[1]

            # replace references with actual blob (base64 or bytes)
            for i, o in enumerate(ornaments):
                if isinstance(o, dict):
                    photo_ref = o.get('item_photo_url')
                else:
                    photo_ref = o[5] if len(o) > 5 else None
                try:
                    did = int(photo_ref)
                except Exception:
                    did = None
                if did and did in blob_map:
                    file_path = blob_map[did]
                    if isinstance(o, dict):
                        o['item_photo_url'] = file_path
                    else:
                        tmp = list(o)
                        tmp[5] = file_path
                        ornaments[i] = tuple(tmp)
    except Exception:
        # don't fail preview/ornament fetch if blob resolution fails
        pass

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
        SELECT document_id, document_type, file_name, file_size_mb, uploaded_at
        FROM gold_schema.account_documents_meta
        WHERE account_id = %s
        ORDER BY uploaded_at DESC
        LIMIT 20
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
        SELECT e.*, m.application_id
        FROM gold_schema.estimation_application_map m
        JOIN gold_schema.estimations e ON e.estimation_id = m.estimation_id
        WHERE m.application_id = %s
        ORDER BY e.estimation_date DESC, e.created_at DESC
        LIMIT 1
        """,
        (application_id,)
    )
    estimation = cur.fetchone()

    estimation_items = []
    if estimation:
        estimation_id = estimation.get('estimation_id') if isinstance(estimation, dict) else estimation[0]
        cur.execute(
            """
            SELECT *
            FROM gold_schema.estimation_items
            WHERE estimation_id = %s
            ORDER BY created_at ASC
            """,
            (estimation_id,)
        )
        estimation_items = cur.fetchall()

    # fetch ornaments for this application so estimation preview can show item photos
    cur.execute(
        """
        SELECT application_id, item_id, item_name, purity_percentage, approx_weight_gms,
               item_photo_url, quantity, created_at
        FROM gold_schema.ornaments
        WHERE application_id = %s
        ORDER BY created_at ASC, item_id ASC
        """,
        (application_id,)
    )
    ornaments = cur.fetchall()

    # If ornaments reference document ids in `item_photo_url`, batch-resolve blobs
    try:
        doc_ids = []
        for o in ornaments:
            if isinstance(o, dict):
                photo_ref = o.get('item_photo_url')
            else:
                photo_ref = o[5] if len(o) > 5 else None
            try:
                did = int(photo_ref)
            except Exception:
                did = None
            if did:
                doc_ids.append(did)

        if doc_ids:
            cur.execute(
                """
                SELECT document_id, file_path
                FROM gold_schema.account_documents
                WHERE document_id = ANY(%s) AND account_id = %s
                """,
                (list(set(doc_ids)), account_id)
            )
            rows = cur.fetchall()
            blob_map = {}
            for r in rows:
                if isinstance(r, dict):
                    blob_map[int(r.get('document_id'))] = r.get('file_path')
                else:
                    blob_map[int(r[0])] = r[1]

            for i, o in enumerate(ornaments):
                if isinstance(o, dict):
                    photo_ref = o.get('item_photo_url')
                else:
                    photo_ref = o[5] if len(o) > 5 else None
                try:
                    did = int(photo_ref)
                except Exception:
                    did = None
                if did and did in blob_map:
                    file_path = blob_map[did]
                    if isinstance(o, dict):
                        o['item_photo_url'] = file_path
                    else:
                        tmp = list(o)
                        tmp[5] = file_path
                        ornaments[i] = tuple(tmp)
    except Exception:
        pass

    return {
        "customer": customer,
        "application": application,
        "addresses": addresses,
        "documents": documents,
        "pledge_details": pledge_details,
        "estimation": estimation,
        "items": estimation_items,
        "ornaments": ornaments
    }


def fetch_payment_preview_context(cur, account_id: int, application_id: int):
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
    documents = fetch_account_documents(cur, account_id)

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
        FROM gold_schema.payment_invoices
        WHERE account_id = %s AND application_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (account_id, application_id)
    )
    invoice = cur.fetchone()

    invoice_items = []
    settlements = []
    if invoice:
        payment_invoice_id = invoice.get('payment_invoice_id') if isinstance(invoice, dict) else invoice[0]
        cur.execute(
            """
            SELECT *
            FROM gold_schema.payment_invoice_items
            WHERE payment_invoice_id = %s
            ORDER BY created_at ASC
            """,
            (payment_invoice_id,)
        )
        invoice_items = cur.fetchall()

        cur.execute(
            """
            SELECT *
            FROM gold_schema.payment_settlements
            WHERE payment_invoice_id = %s
            ORDER BY payment_date DESC, created_at DESC
            """,
            (payment_invoice_id,)
        )
        settlements = cur.fetchall()

    return {
        "customer": customer,
        "application": application,
        "addresses": addresses,
        "documents": documents,
        "pledge_details": pledge_details,
        "invoice": invoice,
        "invoice_items": invoice_items,
        "settlements": settlements
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
                SELECT document_id, document_type, file_name, uploaded_at
                FROM gold_schema.account_documents_meta
        WHERE account_id = %s
          AND document_type ILIKE '%%photo%%'
        ORDER BY uploaded_at DESC
        LIMIT 5
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
        SELECT application_id, item_id, item_name, purity_percentage, approx_weight_gms,
               item_photo_url, quantity, created_at, updated_at
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


def fetch_estimation_summaries_for_account(cur, account_id: int, limit: int = 20):
    """Return lightweight estimation summaries for customer summary endpoint."""
    cur.execute(
        """
        SELECT e.estimation_id,
               e.estimation_no,
               e.estimation_date,
               e.total_net_amount,
               e.created_at,
               m.application_id
        FROM gold_schema.estimations e
        LEFT JOIN gold_schema.estimation_application_map m
            ON e.estimation_id = m.estimation_id
        WHERE e.account_id = %s
        ORDER BY e.estimation_date DESC, e.created_at DESC
        LIMIT %s
        """,
        (account_id, limit)
    )
    return cur.fetchall()


def fetch_invoice_summaries_for_account(cur, account_id: int, limit: int = 20):
    """Return lightweight invoice summaries for customer summary endpoint."""
    cur.execute(
        """
        SELECT payment_invoice_id, invoice_no, invoice_date, total_net_amount, payment_status, application_id, created_at
        FROM gold_schema.payment_invoices
        WHERE account_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (account_id, limit)
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


@app.get("/accounts/documents/{document_id}")
def get_document(document_id: int, mobile: str = Query(...)):
    """Return a single document including its `file_path` (blob) for the owner only."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            SELECT document_id, document_type, file_path, file_name, file_size_mb, uploaded_at
            FROM gold_schema.account_documents
            WHERE document_id = %s AND account_id = %s
            LIMIT 1
            """,
            (document_id, account_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Document not found")
        return row
    finally:
        cur.close()
        conn.close()


@app.get("/accounts/documents/{document_id}/preview")
def preview_document(document_id: int, mobile: str = Query(...)):
    """Return a small preview-friendly data URL for image documents only.

    This keeps list endpoints lightweight and lets the frontend request previews
    on demand using the account owner's `mobile` query param.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            SELECT file_path, file_name
            FROM gold_schema.account_documents
            WHERE document_id = %s AND account_id = %s
            LIMIT 1
            """,
            (document_id, account_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Document not found")

        # handle RealDictCursor or tuple
        if isinstance(row, dict):
            file_path = row.get('file_path')
            file_name = row.get('file_name')
        else:
            file_path = row[0]
            file_name = row[1]

        if not file_path:
            raise HTTPException(404, "No file blob available for preview")

        # determine mime type from filename extension
        mime = 'application/octet-stream'
        if file_name:
            lower = file_name.lower()
            if lower.endswith('.jpg') or lower.endswith('.jpeg'):
                mime = 'image/jpeg'
            elif lower.endswith('.png'):
                mime = 'image/png'
            elif lower.endswith('.gif'):
                mime = 'image/gif'
            elif lower.endswith('.pdf'):
                mime = 'application/pdf'

        content = _normalize_blob(file_path)
        if content is None:
            raise HTTPException(500, "Failed to prepare preview data")

        b64 = base64.b64encode(content).decode('ascii')
        data_url = f"data:{mime};base64,{b64}"

        return {
            "document_id": document_id,
            "file_name": file_name,
            "mime_type": mime,
            "preview_data": data_url
        }
    finally:
        cur.close()
        conn.close()


@app.get("/accounts/documents/{document_id}/download")
def download_document(document_id: int, mobile: str = Query(...)):
    """Stream the raw document bytes with appropriate headers for download."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            SELECT file_path, file_name
            FROM gold_schema.account_documents
            WHERE document_id = %s AND account_id = %s
            LIMIT 1
            """,
            (document_id, account_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Document not found")

        if isinstance(row, dict):
            file_path = row.get('file_path')
            file_name = row.get('file_name')
        else:
            file_path = row[0]
            file_name = row[1]

        if not file_path:
            raise HTTPException(404, "No file blob available")

        content = _normalize_blob(file_path)
        if content is None:
            raise HTTPException(500, "Failed to read file blob")

        # determine mime
        mime = 'application/octet-stream'
        if file_name:
            ln = file_name.lower()
            if ln.endswith('.jpg') or ln.endswith('.jpeg'):
                mime = 'image/jpeg'
            elif ln.endswith('.png'):
                mime = 'image/png'
            elif ln.endswith('.gif'):
                mime = 'image/gif'
            elif ln.endswith('.pdf'):
                mime = 'application/pdf'

        headers = {
            'Content-Disposition': f'attachment; filename="{file_name or document_id}"'
        }

        return StreamingResponse(io.BytesIO(content), media_type=mime, headers=headers)
    finally:
        cur.close()
        conn.close()


@app.get("/accounts/documents/{document_id}/inspect")
def inspect_document(document_id: int, mobile: str = Query(...)):
    """Return diagnostic info about how the file is stored to help debugging.

    Returns pg_typeof(file_path), octet_length (if applicable), and a short hex/base64 sample.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            SELECT pg_typeof(file_path) AS fld_type, file_name, file_path
            FROM gold_schema.account_documents
            WHERE document_id = %s AND account_id = %s
            LIMIT 1
            """,
            (document_id, account_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Document not found")

        # normalize row
        if isinstance(row, dict):
            fld_type = row.get('fld_type')
            file_name = row.get('file_name')
            raw = row.get('file_path')
        else:
            fld_type, file_name, raw = row

        # normalize blob in python for accurate length and hex sample
        content = _normalize_blob(raw)
        bytes_len = len(content) if content is not None else None
        hex_sample = content[:200].hex() if content is not None else None

        return {
            'document_id': document_id,
            'file_name': file_name,
            'pg_type': str(fld_type),
            'bytes': bytes_len,
            'hex_sample': hex_sample
        }
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


def ensure_enquiries_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS gold_schema.enquiries (
            enquiry_id SERIAL PRIMARY KEY,
            account_id INT NULL,
            salutation TEXT,
            name TEXT NOT NULL,
            mobile VARCHAR(32),
            email TEXT,
            branch TEXT,
            enquiry_type TEXT NOT NULL,
            product_interest TEXT,
            source TEXT,
            ornament_type TEXT,
            quantity INT,
            processing_fee NUMERIC(5,2),
            expected_amount NUMERIC(18,2),
            gross_weight_gms NUMERIC(18,4),
            gold_weight_gms NUMERIC(18,4),
            purity_percentage NUMERIC(5,2),
            rate NUMERIC(18,2),
            net_amount NUMERIC(18,2),
            pledge_amount NUMERIC(18,2),
            financier_name TEXT,
            financier_branch TEXT,
            lead_state TEXT,
            lead_status TEXT,
            lead_stage TEXT,
            follow_up_date DATE,
            priority TEXT,
            remarks TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        ALTER TABLE gold_schema.enquiries
            ADD COLUMN IF NOT EXISTS salutation TEXT,
            ADD COLUMN IF NOT EXISTS ornament_type TEXT,
            ADD COLUMN IF NOT EXISTS quantity INT,
            ADD COLUMN IF NOT EXISTS processing_fee NUMERIC(5,2),
            ADD COLUMN IF NOT EXISTS expected_amount NUMERIC(18,2),
            ADD COLUMN IF NOT EXISTS gross_weight_gms NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS gold_weight_gms NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS purity_percentage NUMERIC(5,2),
            ADD COLUMN IF NOT EXISTS rate NUMERIC(18,2),
            ADD COLUMN IF NOT EXISTS net_amount NUMERIC(18,2),
            ADD COLUMN IF NOT EXISTS pledge_amount NUMERIC(18,2),
            ADD COLUMN IF NOT EXISTS financier_name TEXT,
            ADD COLUMN IF NOT EXISTS financier_branch TEXT,
            ADD COLUMN IF NOT EXISTS source TEXT,
            ADD COLUMN IF NOT EXISTS product_interest TEXT,
            ADD COLUMN IF NOT EXISTS lead_state TEXT,
            ADD COLUMN IF NOT EXISTS lead_status TEXT,
            ADD COLUMN IF NOT EXISTS lead_stage TEXT,
            ADD COLUMN IF NOT EXISTS follow_up_date DATE,
            ADD COLUMN IF NOT EXISTS priority TEXT,
            ADD COLUMN IF NOT EXISTS remarks TEXT
        """
    )




def ensure_calculation_entries_table(cur):
    """Table already exists in database - this function is for compatibility"""
    pass


def calc_entry_response(row):
    weight_after_melting = row.get("weight_after_melting")
    purity = row.get("purity")
    refinery_weight = row.get("refinery_weight")
    refinery_purity = row.get("refinery_purity")
    return CalcEntryResponse(
        calc_entry_id=row["calc_entry_id"],
        mobile=row["mobile"],
        application_id=row["application_id"],
        invoice_item_id=row.get("invoice_item_id"),
        application_number=row.get("application_number"),
        invoice_number=row.get("invoice_number"),
        entry_date=row["entry_date"],
        wt_before=None,
        wt_after=weight_after_melting,
        purity_percentage=purity,
        cal_wt_before=None,
        cal_wt_after=refinery_weight,
        cal_purity_percentage=refinery_purity,
        weight_after_melting=weight_after_melting,
        purity=purity,
        fine_weight=row.get("fine_weight"),
        refinery_weight=refinery_weight,
        refinery_purity=refinery_purity,
        refinery_fine_weight=row.get("refinery_fine_weight"),
        difference=row.get("difference"),
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )


@app.post("/enquiries/create", response_model=EnquiryCreateResponse)
def create_enquiry(payload: EnquiryCreateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        ensure_enquiries_table(cur)

        account_id = None
        if payload.mobile:
            cur.execute(
                "SELECT account_id FROM gold_schema.accounts WHERE mobile = %s LIMIT 1",
                (payload.mobile,)
            )
            row = cur.fetchone()
            if row:
                account_id = row[0]

        cur.execute(
            """
            INSERT INTO gold_schema.enquiries (
                account_id, salutation, name, mobile, email, branch,
                enquiry_type, product_interest, source,
                ornament_type, quantity,
                processing_fee, expected_amount,
                gross_weight_gms, gold_weight_gms,
                purity_percentage, rate, net_amount,
                pledge_amount, financier_name, financier_branch,
                lead_state, lead_status, lead_stage,
                follow_up_date, priority, remarks
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING enquiry_id
            """,
            (
                account_id,
                payload.salutation,
                payload.name,
                payload.mobile,
                payload.email,
                payload.branch,
                payload.enquiry_type,
                payload.product_interest,
                payload.source,
                payload.ornament_type,
                payload.quantity,
                payload.processing_fee,
                payload.expected_amount,
                payload.gross_weight_gms,
                payload.gold_weight_gms,
                payload.purity_percentage,
                payload.rate,
                payload.net_amount,
                payload.pledge_amount,
                payload.financier_name,
                payload.financier_branch,
                payload.lead_state,
                payload.lead_status,
                payload.lead_stage,
                payload.follow_up_date,
                payload.priority,
                payload.remarks
            )
        )
        enquiry_id = cur.fetchone()[0]
        conn.commit()
        return {
            "enquiry_id": enquiry_id,
            "status": "created"
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@app.put("/enquiries/update", response_model=EnquiryCreateResponse)
def update_enquiry(payload: EnquiryUpdateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        ensure_enquiries_table(cur)

        cur.execute(
            "SELECT enquiry_id FROM gold_schema.enquiries WHERE enquiry_id = %s",
            (payload.enquiry_id,)
        )
        if not cur.fetchone():
            raise HTTPException(404, "Enquiry not found")

        account_id = None
        if payload.mobile:
            cur.execute(
                "SELECT account_id FROM gold_schema.accounts WHERE mobile = %s LIMIT 1",
                (payload.mobile,)
            )
            row = cur.fetchone()
            if row:
                account_id = row[0]

        update_data = payload.dict(exclude_unset=True)
        update_data.pop("enquiry_id", None)
        update_data["account_id"] = account_id

        if not update_data:
            raise HTTPException(400, "No data provided to update")

        allowed_fields = {
            "account_id", "salutation", "name", "mobile", "email", "branch",
            "enquiry_type", "product_interest", "source",
            "ornament_type", "quantity", "processing_fee",
            "expected_amount", "gross_weight_gms", "gold_weight_gms",
            "purity_percentage", "rate", "net_amount", "pledge_amount",
            "financier_name", "financier_branch", "lead_state",
            "lead_status", "lead_stage", "follow_up_date",
            "priority", "remarks"
        }

        set_clauses = []
        values = []
        for field_name, field_value in update_data.items():
            if field_name not in allowed_fields:
                continue
            set_clauses.append(f"{field_name} = %s")
            values.append(field_value)

        if not set_clauses:
            raise HTTPException(400, "No valid fields provided to update")

        values.append(payload.enquiry_id)
        cur.execute(
            f"""
            UPDATE gold_schema.enquiries
            SET {', '.join(set_clauses)}
            WHERE enquiry_id = %s
            """,
            tuple(values)
        )
        conn.commit()
        return {
            "enquiry_id": payload.enquiry_id,
            "status": "updated"
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/enquiries/by-mobile", response_model=EnquiryListResponse)
def get_enquiries_by_mobile(mobile: str = Query(None, description="Mobile number to filter enquiries")):
    if not mobile:
        raise HTTPException(400, "Mobile parameter is required")

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_enquiries_table(cur)
        cur.execute(
            """
            SELECT enquiry_id, salutation, name, mobile, email, branch,
                   enquiry_type, product_interest, source,
                   ornament_type, processing_fee, expected_amount,
                   gross_weight_gms, gold_weight_gms,
                   purity_percentage, rate, net_amount, pledge_amount,
                   financier_name, financier_branch,
                   lead_state, lead_status, lead_stage,
                   follow_up_date, priority, remarks, created_at
            FROM gold_schema.enquiries
            WHERE mobile = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (mobile,)
        )
        enquiries = cur.fetchall()
        return {"enquiries": enquiries}
    finally:
        cur.close()
        conn.close()


@app.get("/enquiries/by-date", response_model=EnquiryListResponse)
def get_enquiries_by_date(
    date_from: Optional[date] = Query(None, description="Start date in YYYY-MM-DD format"),
    date_to: Optional[date] = Query(None, description="End date in YYYY-MM-DD format"),
    enquiry_type: Optional[str] = Query(None, description="Optional enquiry type filter"),
    branch: Optional[str] = Query(None, description="Optional branch filter"),
    mobile: Optional[str] = Query(None, description="Optional mobile number filter"),
    follow_up_date: Optional[date] = Query(None, description="Optional follow-up date filter"),
    lead_state: Optional[str] = Query(None, description="Optional lead state filter"),
    lead_status: Optional[str] = Query(None, description="Optional lead status filter"),
    lead_stage: Optional[str] = Query(None, description="Optional lead stage filter"),
    sort_order: str = Query("desc", description="Sort order: asc or desc")
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "date_from cannot be greater than date_to")

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_enquiries_table(cur)
        normalized_sort_order = sort_order.lower()
        if normalized_sort_order not in ("asc", "desc"):
            raise HTTPException(400, "sort_order must be asc or desc")

        query = """
            SELECT enquiry_id, salutation, name, mobile, email, branch,
                   enquiry_type, product_interest, source,
                   ornament_type, processing_fee, expected_amount,
                   gross_weight_gms, gold_weight_gms,
                   purity_percentage, rate, net_amount, pledge_amount,
                   financier_name, financier_branch,
                   lead_state, lead_status, lead_stage,
                   follow_up_date, priority, remarks, created_at
            FROM gold_schema.enquiries
            WHERE 1=1
        """
        params = []

        if date_from:
            query += " AND DATE(created_at) >= %s"
            params.append(date_from)

        

        if lead_status:
            query += " AND lead_status = %s"
            params.append(lead_status)

        if lead_stage:
            query += " AND lead_stage = %s"
            params.append(lead_stage)

        query += f" ORDER BY created_at {normalized_sort_order.upper()} LIMIT 200"

        cur.execute(query, tuple(params))
        enquiries = cur.fetchall()
        return {"enquiries": enquiries}
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
            document_id = existing[0]
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
                RETURNING document_id
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
            document_id = cur.fetchone()[0]
        # Upsert metadata into account_documents_meta so list endpoints remain populated
        try:
            cur.execute(
                """
                INSERT INTO gold_schema.account_documents_meta (
                    document_id, account_id, document_type, file_name, file_size_mb, uploaded_at
                ) VALUES (%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                ON CONFLICT (document_id) DO UPDATE
                SET document_type = EXCLUDED.document_type,
                    file_name = EXCLUDED.file_name,
                    file_size_mb = EXCLUDED.file_size_mb,
                    uploaded_at = CURRENT_TIMESTAMP
                """,
                (
                    document_id,
                    account_id,
                    payload.document_type,
                    payload.file_name,
                    payload.file_size_mb
                )
            )
        except Exception:
            # don't fail the whole request if meta upsert fails
            pass

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
        # Also remove metadata entry if present
        try:
            cur.execute(
                """
                DELETE FROM gold_schema.account_documents_meta
                WHERE document_id = %s
                """,
                (document_id,)
            )
        except Exception:
            pass

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


@app.put("/applications/update", response_model=ApplicationResponse)
def update_application(payload: ApplicationUpdateRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, payload.mobile)

        cur.execute(
            """
            SELECT application_id
            FROM gold_schema.applications
            WHERE account_id = %s
              AND application_id = %s
            LIMIT 1
            """,
            (account_id, payload.application_id)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Application not found")

        updates = []
        params = []

        if payload.application_type is not None:
            updates.append('application_type = %s')
            params.append(payload.application_type)
        if payload.application_date is not None:
            updates.append('application_date = %s')
            params.append(payload.application_date)
        if payload.application_no is not None:
            updates.append('application_no = %s')
            params.append(payload.application_no)
        if payload.place is not None:
            updates.append('place = %s')
            params.append(payload.place)
        if payload.status is not None:
            updates.append('status = %s')
            params.append(payload.status)

        if updates:
            params.extend([account_id, payload.application_id])
            cur.execute(
                f"""
                UPDATE gold_schema.applications
                SET {', '.join(updates)}
                WHERE account_id = %s
                  AND application_id = %s
                """,
                tuple(params)
            )

        cur.execute(
            """
            SELECT application_id, application_no, status
            FROM gold_schema.applications
            WHERE account_id = %s AND application_id = %s
            LIMIT 1
            """,
            (account_id, payload.application_id)
        )
        row = cur.fetchone()
        conn.commit()

        return {
            "application_id": row[0],
            "application_no": row[1],
            "status": row[2]
        }
    finally:
        cur.close()
        conn.close()


@app.get("/applications/by-user", response_model=ApplicationListResponse)
def get_applications_by_user(
    mobile: str = Query(...),
    branch_name: str | None = Query(None)
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        if branch_name:
            branch_name = branch_name.strip()
            cur.execute(
                """
                SELECT application_id, application_no,
                       application_type, application_date,
                       place, total_quantity,
                       total_weight_gms, status, created_at
                FROM gold_schema.applications
                WHERE account_id = %s
                  AND place = %s
                ORDER BY created_at DESC
                """,
                (account_id, branch_name)
            )
        else:
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

        kept_item_ids = set()

        # Upsert each ornament and keep track of the rows that should remain.
        for item in payload.ornaments:
            item_id = getattr(item, 'item_id', None)
            if item_id:
                cur.execute(
                    """
                    SELECT 1
                    FROM gold_schema.ornaments
                    WHERE application_id = %s
                      AND item_id = %s
                    LIMIT 1
                    """,
                    (application_id, item_id)
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
                            item_id
                        )
                    )
                    kept_item_ids.add(item_id)
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
                  AND item_id NOT IN %s
                LIMIT 1
                """,
                (
                    application_id,
                    item.item_name,
                    item.purity_percentage,
                    item.approx_weight_gms,
                    item.item_photo_url,
                    tuple(kept_item_ids) if kept_item_ids else (-1,)
                )
            )
            existing = cur.fetchone()

            if existing:
                existing_id = existing[0]
                cur.execute(
                    """
                    UPDATE gold_schema.ornaments
                    SET quantity = %s
                    WHERE item_id = %s
                    """,
                    (
                        item.quantity,
                        existing_id
                    )
                )
                kept_item_ids.add(existing_id)
            else:
                cur.execute(
                    """
                    INSERT INTO gold_schema.ornaments (
                        application_id, item_name,
                        quantity, purity_percentage,
                        approx_weight_gms, item_photo_url
                    )
                    VALUES (%s,%s,%s,%s,%s,%s)
                    RETURNING item_id
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
                new_id = cur.fetchone()[0]
                kept_item_ids.add(new_id)

        if kept_item_ids:
            cur.execute(
                """
                DELETE FROM gold_schema.ornaments
                WHERE application_id = %s
                  AND item_id NOT IN %s
                """,
                (application_id, tuple(kept_item_ids))
            )
        else:
            cur.execute(
                """
                DELETE FROM gold_schema.ornaments
                WHERE application_id = %s
                """,
                (application_id,)
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
        # Invalidate ornament summary cache for this application
        try:
            invalidate_ornament_summary_cache([application_id])
        except Exception:
            pass
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


@app.get("/applications/payment-preview")
def get_payment_preview(
    mobile: str = Query(...),
    application_id: int = Query(...)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        account_id = get_account_id(cur, mobile)
        return fetch_payment_preview_context(cur, account_id, application_id)
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
        # Invalidate ornament summary cache for this application
        try:
            invalidate_ornament_summary_cache([application_id])
        except Exception:
            pass
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

        if getattr(payload, 'application_id', None):
            cur.execute(
                """
                SELECT application_id
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
                raise HTTPException(409, "No active application for estimation")
            application_id = row[0]
        else:
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


@app.delete("/estimations/items")
def delete_estimation_items(mobile: str = Query(...), application_id: int = Query(...), preview: bool = Query(False)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            SELECT e.estimation_id
            FROM gold_schema.estimation_application_map m
            JOIN gold_schema.estimations e ON e.estimation_id = m.estimation_id
            JOIN gold_schema.applications a ON a.application_id = m.application_id
            WHERE a.account_id = %s
              AND m.application_id = %s
            LIMIT 1
            """,
            (account_id, application_id)
        )
        row = cur.fetchone()
        if not row:
            if preview:
                return {"preview": True, "deleted_items": 0}
            raise HTTPException(409, "No estimation found for application")

        estimation_id = row[0]
        if preview:
            cur.execute("SELECT COUNT(*) FROM gold_schema.estimation_items WHERE estimation_id = %s", (estimation_id,))
            count = cur.fetchone()[0] or 0
            return {"preview": True, "estimation_id": estimation_id, "item_count": count}

        cur.execute("DELETE FROM gold_schema.estimation_items WHERE estimation_id = %s", (estimation_id,))
        deleted_items = cur.rowcount
        conn.commit()
        return {"deleted_items": deleted_items, "estimation_id": estimation_id}
    finally:
        cur.close()
        conn.close()


@app.delete("/payments/invoice/items")
def delete_payment_invoice_items(mobile: str = Query(...), application_id: int = Query(...), preview: bool = Query(False)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        cur.execute(
            """
            SELECT payment_invoice_id
            FROM gold_schema.payment_invoices
            WHERE account_id = %s
              AND application_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (account_id, application_id)
        )
        row = cur.fetchone()
        if not row:
            if preview:
                return {"preview": True, "deleted_items": 0}
            raise HTTPException(409, "No invoice found for application")

        invoice_id = row[0]
        if preview:
            cur.execute("SELECT COUNT(*) FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = %s", (invoice_id,))
            count = cur.fetchone()[0] or 0
            return {"preview": True, "payment_invoice_id": invoice_id, "item_count": count}

        cur.execute("DELETE FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = %s", (invoice_id,))
        deleted_items = cur.rowcount
        conn.commit()
        return {"deleted_items": deleted_items, "payment_invoice_id": invoice_id}
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

        if getattr(payload, 'application_id', None):
            cur.execute(
                """
                SELECT application_id
                FROM gold_schema.applications
                WHERE account_id=%s
                  AND application_id=%s
                LIMIT 1
                """,
                (account_id, payload.application_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(409, "No application found for payment")
            application_id = row[0]
            cur.execute(
                """
                SELECT estimation_id
                FROM gold_schema.estimation_application_map
                WHERE application_id=%s
                LIMIT 1
                """,
                (application_id,)
            )
            est_row = cur.fetchone()
            if not est_row:
                raise HTTPException(409, "No estimation found for application")
            estimation_id = est_row[0]
        else:
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

        if getattr(payload, 'application_id', None):
            cur.execute("""
                SELECT payment_invoice_id
                FROM gold_schema.payment_invoices
                WHERE account_id = %s
                  AND application_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (account_id, payload.application_id))
            row = cur.fetchone()
        else:
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


def ensure_vinay_admin(admin_username: str):
    if admin_username != 'vinay':
        raise HTTPException(403, "Only vinay can perform deletion operations")


def _fetch_ids(cur, query: str, params=()):
    cur.execute(query, params)
    return [row[0] for row in cur.fetchall()]


def _count_rows(cur, query: str, params=()):
    cur.execute(query, params)
    row = cur.fetchone()
    return row[0] if row else 0


def _fetch_rows(cur, query: str, params=()):
    cur.execute(query, params)
    return cur.fetchall()


def _sum_column(cur, query: str, params=()):
    cur.execute(query, params)
    row = cur.fetchone()
    value = row[0] if row and row[0] is not None else 0
    return float(value) if value is not None else 0.0


def _delete_by_ids(cur, query: str, ids):
    if not ids:
        return 0
    cur.execute(query, (ids,))
    return cur.rowcount


@app.delete("/deletions/payments")
def delete_payments(mobile: str = Query(...), admin_username: str = Query(...), preview: bool = Query(False), application_id: int = Query(None)):
    ensure_vinay_admin(admin_username)
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        if application_id:
            invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = %s", (account_id, application_id))
        else:
            invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))
        settlement_ids = _fetch_ids(cur, "SELECT settlement_id FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []

        if preview:
            if application_id:
                invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = %s", (account_id, application_id))
            else:
                invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))
            settlement_rows = _fetch_rows(cur, "SELECT payment_mode, paid_amount FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            settlement_value = round(sum(float(row[1] or 0) for row in settlement_rows), 2)
            return {
                "preview": True,
                "deleted_settlements": len(settlement_rows),
                "invoice_count": len(invoice_ids),
                "invoice_numbers": invoice_numbers,
                "settlement_value": settlement_value,
                "settlements": [
                    {
                        "mode": row[0],
                        "amount": round(float(row[1] or 0), 2)
                    }
                    for row in settlement_rows
                ]
            }

        deleted_settlements = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", invoice_ids)
        conn.commit()
        return {
            "deleted_settlements": deleted_settlements,
            "invoice_count": len(invoice_ids)
        }
    finally:
        cur.close()
        conn.close()


@app.delete("/deletions/invoices")
def delete_invoices(
    mobile: str = Query(None),
    admin_username: str = Query(...),
    preview: bool = Query(False),
    application_id: int = Query(None),
    invoice_no: str = Query(None)
):
    ensure_vinay_admin(admin_username)
    conn = get_connection()
    cur = conn.cursor()
    try:
        invoice_no = invoice_no.strip() if invoice_no else None

        if invoice_no:
            if mobile:
                account_id = get_account_id(cur, mobile)
                if application_id:
                    invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = %s AND invoice_no = %s", (account_id, application_id, invoice_no))
                else:
                    invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s AND invoice_no = %s", (account_id, invoice_no))
            else:
                invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE invoice_no = %s", (invoice_no,))
                account_rows = _fetch_rows(cur, "SELECT DISTINCT account_id FROM gold_schema.payment_invoices WHERE invoice_no = %s", (invoice_no,))
                account_id = account_rows[0][0] if account_rows else None
        else:
            if not mobile:
                raise HTTPException(status_code=400, detail="Mobile or invoice number is required")
            account_id = get_account_id(cur, mobile)
            if application_id:
                invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = %s", (account_id, application_id))
            else:
                invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))

        settlement_ids = _fetch_ids(cur, "SELECT settlement_id FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
        item_ids = _fetch_ids(cur, "SELECT invoice_item_id FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []

        if preview:
            invoice_detail_rows = _fetch_rows(cur, """
                SELECT
                    pi.invoice_no,
                    pi.invoice_date,
                    pi.total_net_amount,
                    pi.payment_status,
                    pi.application_id,
                    app.application_no,
                    app.application_type,
                    app.status,
                    app.application_date,
                    app.place,
                    acc.mobile,
                    acc.first_name,
                    acc.last_name
                FROM gold_schema.payment_invoices pi
                LEFT JOIN gold_schema.applications app ON pi.application_id = app.application_id
                LEFT JOIN gold_schema.accounts acc ON pi.account_id = acc.account_id
                WHERE pi.payment_invoice_id = ANY(%s)
                ORDER BY pi.invoice_date DESC
            """, (invoice_ids,)) if invoice_ids else []
            if invoice_no:
                invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            elif application_id:
                invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = %s", (account_id, application_id))
            else:
                invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))
            item_rows = _fetch_rows(cur, "SELECT item_name, net_amount FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            settlement_rows = _fetch_rows(cur, "SELECT payment_mode, paid_amount FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            invoice_value = round(sum(float(row[0] or 0) for row in _fetch_rows(cur, "SELECT total_net_amount FROM gold_schema.payment_invoices WHERE payment_invoice_id = ANY(%s)", (invoice_ids,))), 2) if invoice_ids else 0
            settlement_value = round(sum(float(row[1] or 0) for row in settlement_rows), 2)
            return {
                "preview": True,
                "invoice_no": invoice_no,
                "invoice_details": [
                    {
                        "invoice_no": row[0],
                        "invoice_date": str(row[1]) if row[1] else None,
                        "total_net_amount": round(float(row[2] or 0), 2),
                        "payment_status": row[3],
                        "application_id": row[4],
                        "application_no": row[5],
                        "application_type": row[6],
                        "application_status": row[7],
                        "application_date": str(row[8]) if row[8] else None,
                        "branch": row[9],
                        "mobile": row[10],
                        "customer_name": " ".join(part for part in [row[11], row[12]] if part)
                    }
                    for row in invoice_detail_rows
                ],
                "deleted_settlements": len(settlement_rows),
                "deleted_items": len(item_rows),
                "deleted_invoices": len(invoice_ids),
                "invoice_numbers": invoice_numbers,
                "invoice_value": invoice_value,
                "settlement_value": settlement_value,
                "invoice_items": [
                    {
                        "name": row[0],
                        "amount": round(float(row[1] or 0), 2)
                    }
                    for row in item_rows
                ],
                "settlements": [
                    {
                        "mode": row[0],
                        "amount": round(float(row[1] or 0), 2)
                    }
                    for row in settlement_rows
                ]
            }

        deleted_settlements = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", invoice_ids)
        deleted_items = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", invoice_ids)
        cur.execute("DELETE FROM gold_schema.payment_invoices WHERE payment_invoice_id = ANY(%s)", (invoice_ids,))
        deleted_invoices = cur.rowcount
        conn.commit()
        return {
            "deleted_settlements": deleted_settlements,
            "deleted_items": deleted_items,
            "deleted_invoices": deleted_invoices
        }
    finally:
        cur.close()
        conn.close()


@app.delete("/deletions/transactions")
def delete_transactions(mobile: str = Query(...), admin_username: str = Query(...), preview: bool = Query(False), application_id: int = Query(None)):
    ensure_vinay_admin(admin_username)
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        if application_id:
            invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = %s", (account_id, application_id))
        else:
            invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))
        item_ids = _fetch_ids(cur, "SELECT invoice_item_id FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
        calculation_ids = _fetch_ids(cur, "SELECT calc_entry_id FROM gold_schema.calculation_entries WHERE invoice_item_id = ANY(%s)", (item_ids,)) if item_ids else []

        if preview:
            if application_id:
                invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = %s", (account_id, application_id))
            else:
                invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))
            item_rows = _fetch_rows(cur, "SELECT item_name, net_amount FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            settlement_rows = _fetch_rows(cur, "SELECT payment_mode, paid_amount FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            transaction_value = round(sum(float(row[1] or 0) for row in item_rows), 2)
            settlement_value = round(sum(float(row[1] or 0) for row in settlement_rows), 2)
            return {
                "preview": True,
                "deleted_calculation_entries": len(calculation_ids),
                "deleted_settlements": len(settlement_rows),
                "deleted_items": len(item_rows),
                "invoice_numbers": invoice_numbers,
                "transaction_value": transaction_value,
                "settlement_value": settlement_value,
                "transaction_items": [
                    {
                        "name": row[0],
                        "amount": round(float(row[1] or 0), 2)
                    }
                    for row in item_rows
                ]
            }

        deleted_calculations = _delete_by_ids(cur, "DELETE FROM gold_schema.calculation_entries WHERE invoice_item_id = ANY(%s)", item_ids)
        deleted_settlements = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", invoice_ids)
        deleted_items = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", invoice_ids)
        conn.commit()
        return {
            "deleted_calculation_entries": deleted_calculations,
            "deleted_settlements": deleted_settlements,
            "deleted_items": deleted_items
        }
    finally:
        cur.close()
        conn.close()


@app.delete("/deletions/applications")
def delete_applications(mobile: str = Query(...), admin_username: str = Query(...), preview: bool = Query(False), application_id: int = Query(None)):
    ensure_vinay_admin(admin_username)
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        if application_id:
            application_ids = _fetch_ids(cur, "SELECT application_id FROM gold_schema.applications WHERE account_id = %s AND application_id = %s", (account_id, application_id))
        else:
            application_ids = _fetch_ids(cur, "SELECT application_id FROM gold_schema.applications WHERE account_id = %s", (account_id,))

        if application_ids:
            invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = ANY(%s)", (account_id, application_ids))
        else:
            invoice_ids = []
        item_ids = _fetch_ids(cur, "SELECT invoice_item_id FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []

        if preview:
            application_numbers = _fetch_ids(cur, "SELECT application_no FROM gold_schema.applications WHERE account_id = %s", (account_id,))
            ornament_rows = _fetch_rows(cur, "SELECT item_name, quantity, approx_weight_gms FROM gold_schema.ornaments WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else []
            if application_ids:
                invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE account_id = %s AND application_id = ANY(%s)", (account_id, application_ids))
            else:
                invoice_numbers = []
            settlement_rows = _fetch_rows(cur, "SELECT payment_mode, paid_amount FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            invoice_value = round(sum(float(row[0] or 0) for row in _fetch_rows(cur, "SELECT total_net_amount FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))), 2)
            settlement_value = round(sum(float(row[1] or 0) for row in settlement_rows), 2)
            pledge_rows = _fetch_rows(cur, "SELECT pledge_id, pledger_name, financier_name, principal_amount, total_due FROM gold_schema.pledge_details WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else []
            return {
                "preview": True,
                "deleted_application_mappings": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.estimation_application_map WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else 0,
                "deleted_pledge_details": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.pledge_details WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else 0,
                "deleted_ornaments": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.ornaments WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else 0,
                "deleted_calculation_entries": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.calculation_entries WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else 0,
                "deleted_settlements": len(settlement_rows),
                "deleted_invoice_items": len(item_ids),
                "deleted_invoices": len(invoice_ids),
                "deleted_estimation_items": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.estimation_items WHERE estimation_id IN (SELECT estimation_id FROM gold_schema.estimation_application_map WHERE application_id = ANY(%s))", (application_ids,)) if application_ids else 0,
                "deleted_estimations": 0,
                "deleted_applications": len(application_ids),
                "application_numbers": application_numbers,
                "ornaments": [
                    {
                        "name": row[0],
                        "quantity": row[1],
                        "weight_gms": round(float(row[2] or 0), 3)
                    }
                    for row in ornament_rows
                ],
                "invoice_numbers": invoice_numbers,
                "invoice_value": invoice_value,
                "settlement_value": settlement_value,
                "pledges": [
                    {
                        "pledge_id": row[0],
                        "pledger_name": row[1],
                        "financier_name": row[2],
                        "principal_amount": float(row[3]) if row[3] is not None else 0.0,
                        "total_due": float(row[4]) if row[4] is not None else 0.0
                    }
                    for row in pledge_rows
                ]
            }

        deleted_application_maps = _delete_by_ids(cur, "DELETE FROM gold_schema.estimation_application_map WHERE application_id = ANY(%s)", application_ids) if application_ids else 0
        deleted_pledge = _delete_by_ids(cur, "DELETE FROM gold_schema.pledge_details WHERE application_id = ANY(%s)", application_ids) if application_ids else 0
        deleted_ornaments = _delete_by_ids(cur, "DELETE FROM gold_schema.ornaments WHERE application_id = ANY(%s)", application_ids) if application_ids else 0
        deleted_calc_entries = _delete_by_ids(cur, "DELETE FROM gold_schema.calculation_entries WHERE application_id = ANY(%s)", application_ids) if application_ids else 0
        deleted_settlements = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", invoice_ids) if invoice_ids else 0
        deleted_items = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", invoice_ids) if invoice_ids else 0
        deleted_invoices = 0
        if invoice_ids:
            cur.execute("DELETE FROM gold_schema.payment_invoices WHERE account_id = %s AND payment_invoice_id = ANY(%s)", (account_id, invoice_ids))
            deleted_invoices = cur.rowcount

        deleted_estimation_items = _delete_by_ids(cur, "DELETE FROM gold_schema.estimation_items WHERE estimation_id IN (SELECT estimation_id FROM gold_schema.estimation_application_map WHERE application_id = ANY(%s))", (application_ids,)) if application_ids else 0
        deleted_estimations = 0
        # For application-scoped delete, do not remove estimations themselves (they may be shared). Full-account delete (no application_id) still removes estimations.
        if not application_id:
            deleted_estimations = 0
            cur.execute("DELETE FROM gold_schema.estimations WHERE account_id = %s", (account_id,))
            deleted_estimations = cur.rowcount
        deleted_applications = 0
        if application_ids:
            cur.execute("DELETE FROM gold_schema.applications WHERE account_id = %s AND application_id = ANY(%s)", (account_id, application_ids))
            deleted_applications = cur.rowcount

        conn.commit()
        return {
            "deleted_application_mappings": deleted_application_maps,
            "deleted_pledge_details": deleted_pledge,
            "deleted_ornaments": deleted_ornaments,
            "deleted_calculation_entries": deleted_calc_entries,
            "deleted_settlements": deleted_settlements,
            "deleted_invoice_items": deleted_items,
            "deleted_invoices": deleted_invoices,
            "deleted_estimation_items": deleted_estimation_items,
            "deleted_estimations": deleted_estimations,
            "deleted_applications": deleted_applications
        }
    finally:
        cur.close()
        conn.close()


@app.delete("/deletions/all")
def delete_all_records(mobile: str = Query(...), admin_username: str = Query(...), preview: bool = Query(False)):
    ensure_vinay_admin(admin_username)
    conn = get_connection()
    cur = conn.cursor()
    try:
        account_id = get_account_id(cur, mobile)
        application_ids = _fetch_ids(cur, "SELECT application_id FROM gold_schema.applications WHERE account_id = %s", (account_id,))
        invoice_ids = _fetch_ids(cur, "SELECT payment_invoice_id FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))
        item_ids = _fetch_ids(cur, "SELECT invoice_item_id FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []

        if preview:
            application_numbers = _fetch_ids(cur, "SELECT application_no FROM gold_schema.applications WHERE account_id = %s", (account_id,))
            ornament_rows = _fetch_rows(cur, "SELECT item_name, quantity, approx_weight_gms FROM gold_schema.ornaments WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else []
            invoice_numbers = _fetch_ids(cur, "SELECT invoice_no FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))
            item_rows = _fetch_rows(cur, "SELECT item_name, net_amount FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            settlement_rows = _fetch_rows(cur, "SELECT payment_mode, paid_amount FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", (invoice_ids,)) if invoice_ids else []
            invoice_value = round(sum(float(row[0] or 0) for row in _fetch_rows(cur, "SELECT total_net_amount FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))), 2)
            settlement_value = round(sum(float(row[1] or 0) for row in settlement_rows), 2)
            transaction_value = round(sum(float(row[1] or 0) for row in item_rows), 2)
            return {
                "preview": True,
                "deleted_application_mappings": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.estimation_application_map WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else 0,
                "deleted_pledge_details": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.pledge_details WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else 0,
                "deleted_ornaments": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.ornaments WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else 0,
                "deleted_calculation_entries_by_app": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.calculation_entries WHERE application_id = ANY(%s)", (application_ids,)) if application_ids else 0,
                "deleted_calculation_entries_by_item": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.calculation_entries WHERE invoice_item_id = ANY(%s)", (item_ids,)) if item_ids else 0,
                "deleted_settlements": len(settlement_rows),
                "deleted_invoice_items": len(item_rows),
                "deleted_invoices": len(invoice_ids),
                "deleted_estimation_items": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.estimation_items WHERE estimation_id IN (SELECT estimation_id FROM gold_schema.estimations WHERE account_id = %s)", (account_id,)),
                "deleted_estimations": _count_rows(cur, "SELECT COUNT(*) FROM gold_schema.estimations WHERE account_id = %s", (account_id,)),
                "deleted_applications": len(application_ids),
                "application_numbers": application_numbers,
                "ornaments": [
                    {
                        "name": row[0],
                        "quantity": row[1],
                        "weight_gms": round(float(row[2] or 0), 3)
                    }
                    for row in ornament_rows
                ],
                "invoice_numbers": invoice_numbers,
                "invoice_value": invoice_value,
                "settlement_value": settlement_value,
                "transaction_value": transaction_value,
                "transaction_items": [
                    {
                        "name": row[0],
                        "amount": round(float(row[1] or 0), 2)
                    }
                    for row in item_rows
                ]
            }

        deleted_application_maps = _delete_by_ids(cur, "DELETE FROM gold_schema.estimation_application_map WHERE application_id = ANY(%s)", application_ids)
        deleted_pledge = _delete_by_ids(cur, "DELETE FROM gold_schema.pledge_details WHERE application_id = ANY(%s)", application_ids)
        deleted_ornaments = _delete_by_ids(cur, "DELETE FROM gold_schema.ornaments WHERE application_id = ANY(%s)", application_ids)
        deleted_calc_entries_by_app = _delete_by_ids(cur, "DELETE FROM gold_schema.calculation_entries WHERE application_id = ANY(%s)", application_ids)
        deleted_calculations_by_item = _delete_by_ids(cur, "DELETE FROM gold_schema.calculation_entries WHERE invoice_item_id = ANY(%s)", item_ids)
        deleted_settlements = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_settlements WHERE payment_invoice_id = ANY(%s)", invoice_ids)
        deleted_items = _delete_by_ids(cur, "DELETE FROM gold_schema.payment_invoice_items WHERE payment_invoice_id = ANY(%s)", invoice_ids)
        deleted_invoices = 0
        if invoice_ids:
            cur.execute("DELETE FROM gold_schema.payment_invoices WHERE account_id = %s", (account_id,))
            deleted_invoices = cur.rowcount
        deleted_estimation_items = _delete_by_ids(cur, "DELETE FROM gold_schema.estimation_items WHERE estimation_id IN (SELECT estimation_id FROM gold_schema.estimations WHERE account_id = %s)", (account_id,))
        deleted_estimations = 0
        cur.execute("DELETE FROM gold_schema.estimations WHERE account_id = %s", (account_id,))
        deleted_estimations = cur.rowcount
        deleted_applications = 0
        if application_ids:
            cur.execute("DELETE FROM gold_schema.applications WHERE account_id = %s", (account_id,))
            deleted_applications = cur.rowcount

        conn.commit()
        return {
            "deleted_application_mappings": deleted_application_maps,
            "deleted_pledge_details": deleted_pledge,
            "deleted_ornaments": deleted_ornaments,
            "deleted_calculation_entries_by_app": deleted_calc_entries_by_app,
            "deleted_calculation_entries_by_item": deleted_calculations_by_item,
            "deleted_settlements": deleted_settlements,
            "deleted_invoice_items": deleted_items,
            "deleted_invoices": deleted_invoices,
            "deleted_estimation_items": deleted_estimation_items,
            "deleted_estimations": deleted_estimations,
            "deleted_applications": deleted_applications
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
    # Use a short-lived in-memory cache to avoid repeated expensive fetches
    cache_key = f"{mobile}|{include}"
    now = time.time()
    with _SUMMARY_CACHE_LOCK:
        cached = _SUMMARY_CACHE.get(cache_key)
        if cached and now - cached[0] < _SUMMARY_CACHE_TTL:
            return cached[1]

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        start_all = time.time()
        customer = fetch_customer_by_mobile(cur, mobile)
        account_id = customer["account_id"]
        result = {"customer": customer}

        include_list = [item.strip() for item in include.split(',') if item.strip()]
        include_set = set(include_list)
        application_ids = None

        # Helper to time each fetch and print slow operations
        def timed_fetch(name, fn, *args, **kwargs):
            t0 = time.time()
            res = fn(*args, **kwargs)
            t1 = time.time()
            duration = (t1 - t0) * 1000.0
            if duration > 200:
                print(f"[SLOW QUERY] {name} took {duration:.1f} ms")
            return res

        if "applications" in include_set:
            applications = timed_fetch('fetch_applications_for_account', fetch_applications_for_account, cur, account_id)
            result["applications"] = applications
            application_ids = [app["application_id"] for app in applications]

        if "estimations" in include_set:
            # use lightweight summaries for estimations to avoid fetching all items in summary
            result["estimations"] = timed_fetch('fetch_estimation_summaries_for_account', fetch_estimation_summaries_for_account, cur, account_id)

        if "invoices" in include_set:
            # use lightweight summaries for invoices to avoid fetching items/settlements in summary
            result["invoices"] = timed_fetch('fetch_invoice_summaries_for_account', fetch_invoice_summaries_for_account, cur, account_id)

        if "addresses" in include_set:
            result["addresses"] = timed_fetch('fetch_account_addresses', fetch_account_addresses, cur, account_id)

        if "bank_accounts" in include_set:
            result["bank_accounts"] = timed_fetch('fetch_bank_accounts', fetch_bank_accounts, cur, account_id)

        if "documents" in include_set:
            result["documents"] = timed_fetch('fetch_account_documents', fetch_account_documents, cur, account_id)

        if "ornaments" in include_set or "pledge_details" in include_set:
            if application_ids is None:
                application_ids = timed_fetch('fetch_application_ids', fetch_application_ids, cur, account_id)

            if "ornaments" in include_set:
                # return a lightweight ornaments summary (counts/totals) instead of full rows
                result["ornaments"] = timed_fetch('fetch_ornament_summaries_for_applications', fetch_ornament_summaries_for_applications, cur, application_ids)

            if "pledge_details" in include_set:
                result["pledge_details"] = timed_fetch('fetch_pledge_details_for_applications', fetch_pledge_details_for_applications, cur, application_ids)

        total_ms = (time.time() - start_all) * 1000.0
        if total_ms > 300:
            print(f"[SLOW SUMMARY] total customer summary for {mobile} took {total_ms:.1f} ms (include={include})")

        # Cache the result briefly
        with _SUMMARY_CACHE_LOCK:
            _SUMMARY_CACHE[cache_key] = (time.time(), result)

        return result
    finally:
        cur.close()
        conn.close()


@app.post("/calc-entries/create", response_model=CalcEntryResponse)
def create_calc_entry(payload: CalcEntryCreateRequest):
    """Create or update a calculated transaction manual entry."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_calculation_entries_table(cur)
        conn.commit()

        account_id = get_account_id(cur, payload.mobile)
        
        cur.execute(
            """
            SELECT calc_entry_id FROM gold_schema.calculation_entries
            WHERE account_id = %s
              AND application_id = %s
              AND entry_date = %s
              AND invoice_item_id IS NOT DISTINCT FROM %s
            """,
            (account_id, payload.application_id, payload.entry_date, payload.invoice_item_id)
        )
        existing = cur.fetchone()

        if existing:
            cur.execute(
                """
                UPDATE gold_schema.calculation_entries
                SET mobile = %s,
                    invoice_item_id = %s,
                    application_number = %s,
                    invoice_number = %s,
                    weight_after_melting = %s,
                    purity = %s,
                    refinery_weight = %s,
                    refinery_purity = %s,
                    updated_at = NOW()
                WHERE calc_entry_id = %s
                RETURNING *
                """,
                (
                    payload.mobile,
                    payload.invoice_item_id,
                    payload.application_number,
                    payload.invoice_number,
                    payload.wt_after or 0,
                    payload.purity_percentage or 0,
                    payload.cal_wt_after,
                    payload.cal_purity_percentage,
                    existing["calc_entry_id"]
                )
            )
        else:
            cur.execute(
                """
                INSERT INTO gold_schema.calculation_entries (
                    account_id, application_id, invoice_item_id,
                    application_number, invoice_number, entry_date, mobile,
                    weight_after_melting, purity, refinery_weight, refinery_purity
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    account_id,
                    payload.application_id,
                    payload.invoice_item_id,
                    payload.application_number,
                    payload.invoice_number,
                    payload.entry_date,
                    payload.mobile,
                    payload.wt_after or 0,
                    payload.purity_percentage or 0,
                    payload.cal_wt_after,
                    payload.cal_purity_percentage
                )
            )

        row = cur.fetchone()
        conn.commit()
        
        return calc_entry_response(row)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/calc-entries/all")
def get_all_calc_entries():
    """Get all calculated transaction manual entries."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_calculation_entries_table(cur)
        conn.commit()

        cur.execute(
            """
            SELECT calc_entry_id, account_id, application_id, invoice_item_id,
                   application_number, invoice_number, entry_date, mobile,
                   weight_after_melting, purity, fine_weight,
                   refinery_weight, refinery_purity, refinery_fine_weight, difference,
                   created_at, updated_at
            FROM gold_schema.calculation_entries
            ORDER BY entry_date DESC, created_at DESC
            """
        )
        return {"entries": cur.fetchall()}
    finally:
        cur.close()
        conn.close()


@app.get("/calc-entries/by-mobile", response_model=CalcEntryListResponse)
def get_calc_entries_by_mobile(mobile: str = Query(...)):
    """Get all calculation entries for a customer"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_calculation_entries_table(cur)
        conn.commit()

        account_id = get_account_id(cur, mobile)
        
        cur.execute(
            """
            SELECT calc_entry_id, account_id, application_id, invoice_item_id,
                   application_number, invoice_number, entry_date, mobile,
                   weight_after_melting, purity, fine_weight,
                   refinery_weight, refinery_purity, refinery_fine_weight, difference,
                   created_at, updated_at
            FROM gold_schema.calculation_entries
            WHERE account_id = %s OR mobile = %s
            ORDER BY entry_date DESC, created_at DESC
            """,
            (account_id, mobile)
        )
        
        rows = cur.fetchall()
        entries = [calc_entry_response(r) for r in rows]
        
        return CalcEntryListResponse(mobile=mobile, entries=entries)
    finally:
        cur.close()
        conn.close()


@app.put("/calc-entries/{calc_entry_id}", response_model=CalcEntryResponse)
def update_calc_entry(calc_entry_id: int, payload: CalcEntryUpdateRequest, mobile: str = Query(...)):
    """Update manual calculation fields for an entry"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ensure_calculation_entries_table(cur)
        conn.commit()

        account_id = get_account_id(cur, mobile)
        
        # Verify entry exists and belongs to this account
        cur.execute(
            """
            SELECT * FROM gold_schema.calculation_entries
            WHERE calc_entry_id = %s AND account_id = %s
            """,
            (calc_entry_id, account_id)
        )
        
        entry = cur.fetchone()
        if not entry:
            raise HTTPException(404, "Calculation entry not found")
        
        update_data = payload.dict(exclude_unset=True)
        field_map = {
            "application_number": "application_number",
            "invoice_number": "invoice_number",
            "wt_after": "weight_after_melting",
            "purity_percentage": "purity",
            "cal_wt_after": "refinery_weight",
            "cal_purity_percentage": "refinery_purity"
        }
        update_fields = []
        values = []
        for field_name, field_value in update_data.items():
            column_name = field_map.get(field_name)
            if not column_name:
                continue
            update_fields.append(f"{column_name} = %s")
            values.append(field_value)
        
        if not update_fields:
            raise HTTPException(400, "No fields provided to update")
        
        update_fields.append("updated_at = NOW()")
        values.append(calc_entry_id)
        
        cur.execute(
            f"""
            UPDATE gold_schema.calculation_entries
            SET {', '.join(update_fields)}
            WHERE calc_entry_id = %s
            RETURNING *
            """,
            tuple(values)
        )
        
        updated_entry = cur.fetchone()
        conn.commit()
        
        return calc_entry_response(updated_entry)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@app.delete("/calc-entries/{calc_entry_id}")
def delete_calc_entry(calc_entry_id: int, mobile: str = Query(...)):
    """Delete a calculation entry"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        ensure_calculation_entries_table(cur)
        conn.commit()

        account_id = get_account_id(cur, mobile)
        
        # Verify entry exists and belongs to this account
        cur.execute(
            """
            DELETE FROM gold_schema.calculation_entries
            WHERE calc_entry_id = %s AND account_id = %s
            RETURNING calc_entry_id
            """,
            (calc_entry_id, account_id)
        )
        
        if not cur.fetchone():
            raise HTTPException(404, "Calculation entry not found")
        
        conn.commit()
        return {"status": "deleted", "calc_entry_id": calc_entry_id}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
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
                app.application_no,
                app.place AS application_branch,
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
            LEFT JOIN gold_schema.applications app ON pi.application_id = app.application_id
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
def get_estimations_by_user(
    mobile: str = Query(...),
    branch_name: str | None = Query(None)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        account_id = get_account_id(cur, mobile)

        if branch_name:
            branch_name = branch_name.strip()
            cur.execute(
                """
                SELECT e.*
                FROM gold_schema.estimations e
                LEFT JOIN gold_schema.estimation_application_map m
                    ON e.estimation_id = m.estimation_id
                LEFT JOIN gold_schema.applications a
                    ON m.application_id = a.application_id
                WHERE e.account_id = %s
                  AND a.place = %s
                ORDER BY e.estimation_date DESC
                """,
                (account_id, branch_name)
            )
        else:
            cur.execute(
                "SELECT * FROM gold_schema.estimations WHERE account_id=%s ORDER BY estimation_date DESC",
                (account_id,)
            )

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
