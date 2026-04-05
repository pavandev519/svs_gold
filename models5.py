from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import date
from decimal import Decimal


# -------------------------------------------------
# ACCOUNT CHECK
# -------------------------------------------------

class AccountCheckRequest(BaseModel):
    mobile: Optional[str] = None
    email: Optional[EmailStr] = None


class AccountCheckResponse(BaseModel):
    exists: bool
    account_id: Optional[int] = None
    account_code: Optional[str] = None


# -------------------------------------------------
# ACCOUNT CREATE
# -------------------------------------------------

class AccountCreateRequest(BaseModel):
    account_type: str
    account_code: str

    first_name: str
    last_name: str
    mobile: str
    phone: Optional[str] = None #
    email: Optional[EmailStr] = None

    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    aadhar_no: Optional[str] = None

    occupation: Optional[str] = None

    pan_no: Optional[str] = None  

    source: Optional[str] = None  #
    owner: Optional[str] = None   #

    state: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    address_text: Optional[str] = None


class AccountCreateResponse(BaseModel):
    account_id: int
    account_code: str
    name: str
    mobile: str
    email: Optional[EmailStr]


class AccountUpdateRequest(BaseModel):
    account_type: Optional[str] = None
    account_code: Optional[str] = None

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    mobile: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    aadhar_no: Optional[str] = None

    occupation: Optional[str] = None

    pan_no: Optional[str] = None

    source: Optional[str] = None
    owner: Optional[str] = None

    state: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    address_text: Optional[str] = None


# -------------------------------------------------
# ADDRESS
# -------------------------------------------------

class AddressCreateRequest(BaseModel):
    address_type: str
    address_line: str
    street: Optional[str] = None
    city: str
    state: str
    country: Optional[str] = "India"
    pincode: Optional[str] = None


# -------------------------------------------------
# BANK ACCOUNT
# -------------------------------------------------

class BankAccountCreateRequest(BaseModel):
    bank_name: str
    branch: Optional[str] = None
    account_number: str
    ifsc_code: str

    account_holder_name: str
    account_holder_type: Optional[str] = None
    is_primary: bool = False


# -------------------------------------------------
# DOCUMENT METADATA
# -------------------------------------------------

class AccountDocumentCreateRequest(BaseModel):
    document_type: str
    document_number: Optional[str] = None

    file_path: str
    file_name: str
    file_size_mb: Optional[Decimal] = None


# -------------------------------------------------
# APPLICATION
# -------------------------------------------------

class ApplicationCreateRequest(BaseModel):
    mobile: str
    application_type: str
    application_date: date
    application_no: str
    place: str  # Dilsuknagar or narayanaguda


class ApplicationResponse(BaseModel):
    application_id: int
    application_no: str
    status: str


class ApplicationListItem(BaseModel):
    application_id: int
    application_no: str
    application_type: str
    application_date: date
    branch: Optional[str]
    total_quantity: Optional[int]
    total_weight_gms: Optional[float]
    status: str
    created_at: str


class ApplicationListResponse(BaseModel):
    mobile: str
    applications: List[ApplicationListItem]


# -------------------------------------------------
# PLEDGE RELEASE
# -------------------------------------------------

class PledgeDetailsCreateRequest(BaseModel):
    mobile: str

    financier_name: str
    branch_name: Optional[str] = None
    gold_loan_account_no: str
    pledger_address: str
    principal_amount: Decimal
    interest_amount: Optional[Decimal] = None


class PledgeDetailsResponse(BaseModel):
    application_id: int
    pledge_id: int
    status: str


# -------------------------------------------------
# ORNAMENTS
# -------------------------------------------------

class OrnamentItem(BaseModel):
    item_name: str
    quantity: int
    purity_percentage: Decimal
    approx_weight_gms: Decimal
    item_photo_url: str


class OrnamentCreateRequest(BaseModel):
    mobile: str
    ornaments: List[OrnamentItem]


class OrnamentCreateResponse(BaseModel):
    application_id: int
    application_no: str
    total_quantity: int
    total_weight_gms: float
    status: str


# -------------------------------------------------
# ESTIMATION
# -------------------------------------------------

class EstimationItemCreateRequest(BaseModel):
    mobile: str
    estimation_no: str

    item_name: Optional[str] = None
    quantity: int = 1

    gross_weight_gms: Optional[Decimal] = None
    stone_weight_gms: Decimal

    purity_percentage: Optional[Decimal] = None
    gold_rate_per_gm: Decimal

    deduction_percentage: Decimal

    @validator('quantity')
    def quantity_positive(cls, v):
        if v <= 0:
            raise ValueError('quantity must be > 0')
        return v

    @validator('gross_weight_gms')
    def gross_weight_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError('gross_weight_gms must be > 0')
        return v

    @validator('stone_weight_gms')
    def stone_weight_non_negative(cls, v):
        if v < 0:
            raise ValueError('stone_weight_gms must be >= 0')
        return v

    @validator('purity_percentage')
    def purity_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError('purity_percentage must be > 0')
        return v

    @validator('gold_rate_per_gm')
    def rate_positive(cls, v):
        if v <= 0:
            raise ValueError('gold_rate_per_gm must be > 0')
        return v

    @validator('deduction_percentage')
    def deduction_non_negative(cls, v):
        if v < 0 or v > 100:
            raise ValueError('deduction_percentage must be between 0 and 100')
        return v


class EstimationResponse(BaseModel):
    estimation_id: int
    net_weight_gms: Decimal
    gross_amount: Decimal
    net_amount: Decimal
    status: str


# -------------------------------------------------
# PURCHASE
# -------------------------------------------------
# -------------------------------------------------
# PAYMENT INVOICE (HEADER)
# -------------------------------------------------

class PaymentInvoiceCreateRequest(BaseModel):
    mobile: str
    invoice_no: str
    invoice_date: date
    total_net_amount: Decimal
    amount_in_words: Optional[str] = None
    remarks: Optional[str] = None


class PaymentInvoiceResponse(BaseModel):
    payment_invoice_id: int
    invoice_no: str
    payment_status: str

# -------------------------------------------------
# PAYMENT INVOICE ITEMS
# -------------------------------------------------

class PaymentInvoiceItemCreateRequest(BaseModel):
    mobile: str
    item_name: str

    weight_before_melting: Decimal
    weight_after_melting: Decimal

    purity_after_melting: Decimal
    gold_rate_per_gm: Decimal

    gross_amount: Decimal
    #deductions_amount: Decimal
    deduction_percentage: Decimal
    net_amount: Decimal

    @validator('purity_after_melting')
    def purity_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('purity_after_melting must be > 0')
        return v


class PaymentInvoiceItemResponse(BaseModel):
    invoice_item_id: int
    payment_invoice_id: int


# -------------------------------------------------
# PAYMENT DEDUCTIONS
# -------------------------------------------------

class PaymentDeductionCreateRequest(BaseModel):
    invoice_item_id: int
    deduction_type: str  # MELTING | PROCESSING | DOCUMENTATION | OTHER
    #deduction_amount: Decimal
    deduction_percentage: Decimal


class PaymentDeductionResponse(BaseModel):
    deduction_id: int
    invoice_item_id: int

# -------------------------------------------------
# PAYMENT SETTLEMENTS
# -------------------------------------------------

class PaymentSettlementCreateRequest(BaseModel):
    mobile: str
    payment_mode: str  # CASH | UPI | BANK_TRANSFER | CHEQUE
    paid_amount: Decimal
    payment_date: date


class PaymentSettlementResponse(BaseModel):
    settlement_id: int
    payment_invoice_id: int
    paid_amount: Decimal

