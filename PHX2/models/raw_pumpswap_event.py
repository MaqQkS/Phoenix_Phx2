"""Raw PumpSwap event model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PHX2.models.enums import DataStatus
from PHX2.models.serialization import SerializableDataclass


@dataclass(frozen=True)
class RawPumpSwapEvent(SerializableDataclass):
    """PHX2-owned normalized raw PumpSwap/gRPC event."""

    observed_at: datetime
    source: str
    signature: str
    dedupe_key: str
    event_type: str
    id: Optional[int] = None
    subscription: Optional[str] = None
    slot: Optional[int] = None
    block_time: Optional[datetime] = None
    transaction_index: Optional[int] = None
    instruction_index: Optional[int] = None
    inner_instruction_index: Optional[int] = None
    event_index: Optional[int] = None
    pool_address: Optional[str] = None
    token_address: Optional[str] = None
    base_mint: Optional[str] = None
    quote_mint: Optional[str] = None
    user_address: Optional[str] = None
    base_amount_raw: Optional[str] = None
    quote_amount_raw: Optional[str] = None
    base_amount_token: Optional[float] = None
    quote_amount_sol: Optional[float] = None
    price_sol: Optional[float] = None
    price_usd: Optional[float] = None
    mcap: Optional[float] = None
    lp_fee_sol: Optional[float] = None
    protocol_fee_sol: Optional[float] = None
    creator_fee_sol: Optional[float] = None
    total_fee_sol: Optional[float] = None
    fee_unit: Optional[str] = None
    fee_invariant_ok: Optional[bool] = None
    decoder_name: Optional[str] = None
    decoder_version: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    data_status: DataStatus = DataStatus.MISSING
    missing_reasons: List[str] = field(default_factory=list)
