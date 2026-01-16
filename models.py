from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import date
from typing import List
from decimal import Decimal

class AccountCheckRequest(BaseModel):
    mobile: Optional[str] = None
    email: Optional[EmailStr] = None


class AccountCheckResponse(BaseModel):
    account_id: Optional[int] = None
    account_code: Optional[str] = None
    exists: bool
    
class AccountCreateRequest(BaseModel):
    account_type: str
    account_code: Optional[str] = None
    first_name: str
    last_name: str
    mobile: str | None = None
    email: EmailStr | None = None
    city: str | None = None
    state: str | None = None

class AccountCreateResponse(BaseModel):
    account_id: int
    account_code: str
    name: str
    mobile: Optional[str] = None
    email: Optional[EmailStr] = None



class ApplicationCreateRequest(BaseModel):
    mobile: str
    application_type: str              # DIRECT_BUYING | PLEDGE_RELEASE  # fronteend validation
    application_date: Optional[date] = None
    application_no: Optional[str] = None
    place: Optional[str] = None
    # total_quantity: Optional[int] = None
    # total_weight_gms: Optional[float] = None

class ApplicationResponse(BaseModel):
    application_id: int
    application_no: str
    status: str

class ApplicationListItem(BaseModel):
    application_id: int
    application_no: str
    application_type: str
    application_date: date | None
    place: str | None
    total_quantity: int | None
    total_weight_gms: float | None
    status: str
    created_at: str

class ApplicationListResponse(BaseModel):
    mobile: str
    applications: List[ApplicationListItem]

class PledgeDetailsCreateRequest(BaseModel):
    mobile: str
    pledger_name: Optional[str] = None
    pledger_address: Optional[str] = None
    financier_name: Optional[str] = None
    branch_name: Optional[str] = None
    gold_loan_account_no: Optional[str] = None
    authorized_person: Optional[str] = None
    principal_amount: Optional[Decimal] = None
    interest_amount: Optional[Decimal] = None
    total_due: Optional[Decimal] = None
    cheque_no: Optional[str] = None
    cheque_date: Optional[date] = None
    margin_percentage: Optional[Decimal] = None

class PledgeDetailsResponse(BaseModel):
    application_id: int
    pledge_id: int
    status: str

class OrnamentItemRequest(BaseModel):
    item_name: str
    quantity: int
    purity_percentage: Optional[float] = None
    approx_weight_gms: Optional[float] = None
    item_photo_url: Optional[str] = None

class OrnamentCreateRequest(BaseModel):
    mobile: str
    ornaments: List[OrnamentItemRequest]

class OrnamentCreateResponse(BaseModel):
    application_id: int
    application_no: str
    total_quantity: int
    total_weight_gms: float
    status: str

class EstimationItemCreateRequest(BaseModel):
    mobile: str
    item_name: str
    quantity: int = Field(gt=0)
    estimation_no: Optional[str] = None
    gross_weight_gms: Decimal = Field(gt=0)
    stone_weight_gms: Decimal = Field(ge=0)
    purity_percentage: Decimal = Field(gt=0, le=100)
    gold_rate_per_gm: Decimal = Field(gt=0)
    #deductions_amount: Decimal = Decimal("0.00")
    deduction_percentage: Decimal = Field(
    ge=0, le=100,
    description="Deduction percentage on gross gold amount"
)

class EstimationResponse(BaseModel):
    estimation_id: int
    net_weight_gms: float
    gross_amount: float
    net_amount: float
    status: str