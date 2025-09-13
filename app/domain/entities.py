from dataclasses import dataclass
from typing import Optional

@dataclass
class Product:
    id: int
    barcode: str
    name: str
    unit: str
    price_per_unit: float
    active: bool = True

@dataclass
class Batch:
    id: int
    product_id: int
    lot_code: Optional[str]
    expiry_date: Optional[str]
