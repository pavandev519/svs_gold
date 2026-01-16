from pydantic import BaseModel, EmailStr
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
    contact_person: Optional[str] = None

    mobile: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    aadhar_no: Optional[str] = None

    yearly_income: Optional[Decimal] = None
    occupation: Optional[str] = None

    gst_no: Optional[str] = None
    pan_no: Optional[str] = None

    source: Optional[str] = None
    owner: Optional[str] = None

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
    place: Optional[str] = None


class ApplicationResponse(BaseModel):
    application_id: int
    application_no: str
    status: str


class ApplicationListItem(BaseModel):
    application_id: int
    application_no: str
    application_type: str
    application_date: date
    place: Optional[str]
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

    pledger_name: str
    pledger_address: Optional[str] = None

    financier_name: str
    branch_name: Optional[str] = None
    gold_loan_account_no: str
    authorized_person: Optional[str] = None

    principal_amount: Decimal
    interest_amount: Optional[Decimal] = None
    total_due: Decimal

    cheque_no: Optional[str] = None
    cheque_date: Optional[date] = None

    margin_percentage: Optional[Decimal] = None


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
    approx_weight_gms: Optional[Decimal] = None
    item_photo_url: Optional[str] = None


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

    item_name: str
    quantity: int

    gross_weight_gms: Decimal
    stone_weight_gms: Optional[Decimal] = 0

    purity_percentage: Decimal
    gold_rate_per_gm: Decimal

    deduction_percentage: Optional[Decimal] = 0


class EstimationResponse(BaseModel):
    estimation_id: int
    net_weight_gms: Decimal
    gross_amount: Decimal
    net_amount: Decimal
    status: str
