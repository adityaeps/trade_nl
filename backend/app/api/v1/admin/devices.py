from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.deps import get_current_admin
from app.db.session import get_session
from app.models.admin_user import AdminUser
from app.models.device import Brand, Device, DeviceCategory
from app.models.pricing import BasePrice, LiquidityTier

router = APIRouter(prefix="/devices", tags=["admin:devices"])


class AdminDeviceOut(BaseModel):
    id: UUID
    brand: str
    model: str
    storage_gb: int
    color: str | None
    category: str
    has_s_pen: bool
    slug: str
    image_url: str | None
    is_active: bool
    base_price: Decimal | None
    markup_pct: Decimal | None
    liquidity_tier: str | None
    last_synced_at: str | None


class DeviceCreate(BaseModel):
    brand: Brand
    model: str
    storage_gb: int
    color: str | None = None
    category: DeviceCategory = DeviceCategory.phone
    has_s_pen: bool = False
    slug: str
    image_url: str | None = None
    is_active: bool = True


class DeviceUpdate(BaseModel):
    model: str | None = None
    storage_gb: int | None = None
    color: str | None = None
    has_s_pen: bool | None = None
    image_url: str | None = None
    is_active: bool | None = None


class BasePriceUpdate(BaseModel):
    base_price: Decimal
    markup_pct: Decimal
    liquidity_tier: LiquidityTier


def _to_out(device: Device, bp: BasePrice | None) -> AdminDeviceOut:
    return AdminDeviceOut(
        id=device.id,
        brand=device.brand,
        model=device.model,
        storage_gb=device.storage_gb,
        color=device.color,
        category=device.category,
        has_s_pen=device.has_s_pen,
        slug=device.slug,
        image_url=device.image_url,
        is_active=device.is_active,
        base_price=bp.base_price if bp else None,
        markup_pct=bp.markup_pct if bp else None,
        liquidity_tier=bp.liquidity_tier if bp else None,
        last_synced_at=bp.last_synced_at.isoformat() if bp and bp.last_synced_at else None,
    )


def _get_base_price(session: Session, device_id: UUID) -> BasePrice | None:
    return session.exec(select(BasePrice).where(BasePrice.device_id == device_id)).first()


@router.get("", response_model=list[AdminDeviceOut])
def list_devices(
    brand: Brand | None = None,
    search: str | None = None,
    include_inactive: bool = True,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    # One outer join, not one query per device. This used to run a separate
    # BasePrice lookup for every row - fine for the 11-device seed set, but
    # the real catalog is ~230 devices, so opening the Catalog or Pricing
    # page meant 230+ sequential round trips before anything rendered.
    query = select(Device, BasePrice).join(
        BasePrice, BasePrice.device_id == Device.id, isouter=True
    )
    if brand:
        query = query.where(Device.brand == brand)
    if search:
        query = query.where(Device.model.ilike(f"%{search}%"))
    if not include_inactive:
        query = query.where(Device.is_active == True)  # noqa: E712
    rows = session.exec(query.order_by(Device.brand, Device.model, Device.storage_gb)).all()
    return [_to_out(d, bp) for d, bp in rows]


@router.post("", response_model=AdminDeviceOut, status_code=201)
def create_device(
    payload: DeviceCreate,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    if session.exec(select(Device).where(Device.slug == payload.slug)).first():
        raise HTTPException(status_code=409, detail=f"Slug '{payload.slug}' already exists")
    device = Device(**payload.model_dump())
    session.add(device)
    session.commit()
    session.refresh(device)
    return _to_out(device, None)


@router.put("/{device_id}", response_model=AdminDeviceOut)
def update_device(
    device_id: UUID,
    payload: DeviceUpdate,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    session.add(device)
    session.commit()
    session.refresh(device)
    return _to_out(device, _get_base_price(session, device.id))


@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: UUID,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    # Soft delete: quotes reference devices and ARCHITECTURE.md §2 requires
    # historical quotes stay intact, so deactivate rather than hard-delete.
    device.is_active = False
    session.add(device)
    session.commit()


@router.put("/{device_id}/base-price", response_model=AdminDeviceOut)
def upsert_base_price(
    device_id: UUID,
    payload: BasePriceUpdate,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if payload.base_price < 0:
        raise HTTPException(status_code=422, detail="base_price cannot be negative")

    bp = _get_base_price(session, device_id)
    if bp:
        bp.base_price = payload.base_price
        bp.markup_pct = payload.markup_pct
        bp.liquidity_tier = payload.liquidity_tier
    else:
        bp = BasePrice(
            device_id=device_id,
            base_price=payload.base_price,
            markup_pct=payload.markup_pct,
            liquidity_tier=payload.liquidity_tier,
        )
    session.add(bp)
    session.commit()
    session.refresh(device)
    return _to_out(device, bp)
