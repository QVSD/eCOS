from typing import Optional, List, Dict, Any
from ..infra.db import connect

def lei_to_cents(lei: float | str | None) -> Optional[int]:
    if lei is None:
        return None
    return int(round(float(lei) * 100))

def cents_to_lei(cents: int | None) -> float:
    return 0.0 if cents is None else cents / 100.0

def to_base_qty(unit: str, qty: float) -> int:
    # unități de bază: buc/grame/ml
    if unit == 'buc':
        return int(round(qty))
    elif unit in ('kg', 'l'):
        return int(round(qty * 1000))
    else:
        raise ValueError(f"Unitate necunoscută: {unit}")

class InventoryService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # ---------- PRODUSE ----------
    def find_product_by_barcode(self, barcode: str) -> Optional[Dict[str, Any]]:
        conn = connect(self.db_path)
        row = conn.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
        return dict(row) if row else None

    def create_product(self, *, barcode: str, name: str, unit: str='buc', price_per_unit_lei: float=0.0) -> int:
        conn = connect(self.db_path)
        with conn:
            cur = conn.execute(
                "INSERT INTO products(barcode, name, unit, price_per_unit_cents) VALUES(?,?,?,?)",
                (barcode, name, unit, lei_to_cents(price_per_unit_lei))
            )
            return cur.lastrowid

    def get_or_create_product(self, *, barcode: str, name: Optional[str], unit: str, price_per_unit_lei: float=0.0) -> Dict[str, Any]:
        p = self.find_product_by_barcode(barcode)
        if p:
            return p
        if not name:
            name = f"Produs {barcode}"
        pid = self.create_product(barcode=barcode, name=name, unit=unit, price_per_unit_lei=price_per_unit_lei)
        return {"id": pid, "barcode": barcode, "name": name, "unit": unit}

    # ---------- LOTURI ----------
    def get_or_create_batch(self, product_id: int, expiry_date: Optional[str], lot_code: Optional[str]) -> Optional[int]:
        if not expiry_date and not lot_code:
            return None
        conn = connect(self.db_path)
        with conn:
            row = conn.execute(
                "SELECT id FROM batches WHERE product_id=? AND IFNULL(expiry_date,'')=IFNULL(?, '') AND IFNULL(lot_code,'')=IFNULL(?, '')",
                (product_id, expiry_date, lot_code)
            ).fetchone()
            if row:
                return row["id"]
            cur = conn.execute(
                "INSERT INTO batches(product_id, expiry_date, lot_code) VALUES(?,?,?)",
                (product_id, expiry_date, lot_code)
            )
            return cur.lastrowid

    # ---------- SESIUNI INTRARE ----------
    def start_stock_in_session(self, note: str='') -> int:
        conn = connect(self.db_path)
        with conn:
            cur = conn.execute("INSERT INTO stock_in_sessions(note) VALUES(?)", (note,))
            return cur.lastrowid

    def add_stock_in_line(
        self,
        *,
        session_id: int,
        barcode: str,
        quantity: float,
        product_name: Optional[str],
        unit: str='buc',
        price_per_unit_lei: float=0.0,
        expiry_date: Optional[str]=None,   # 'YYYY-MM-DD'
        lot_code: Optional[str]=None,
        unit_cost_lei: Optional[float]=None,
        supplier_name: Optional[str]=None,
        supplier_doc: Optional[str]=None
    ) -> int:
        conn = connect(self.db_path)
        with conn:
            # produs (folosim unitatea din produs dacă există)
            p = self.find_product_by_barcode(barcode)
            if p is None:
                p = self.get_or_create_product(barcode=barcode, name=product_name, unit=unit, price_per_unit_lei=price_per_unit_lei)
            product_id = p["id"]
            prod_unit = p.get("unit", unit)

            # lot (opțional)
            batch_id = self.get_or_create_batch(product_id, expiry_date, lot_code)

            # cantitatea în unități de bază
            qty_base = to_base_qty(prod_unit, quantity)

            # cost unitar (cents) – opțional
            unit_cost_cents = lei_to_cents(unit_cost_lei)

            # doar linia în sesiune (NU scriem mișcarea încă!)
            cur = conn.execute("""
                INSERT INTO stock_in_lines(session_id, product_id, batch_id, quantity_base, unit_cost_cents, supplier_name, supplier_doc)
                VALUES(?,?,?,?,?,?,?)
            """, (session_id, product_id, batch_id, qty_base, unit_cost_cents, supplier_name, supplier_doc))
            return cur.lastrowid

    def close_stock_in_session(self, session_id: int):
        """
        La închidere: grupează liniile pe (product_id, batch_id) și scrie o singură mișcare 'stock_in' per grup.
        Apoi setează closed_at.
        """
        conn = connect(self.db_path)
        with conn:
            rows = conn.execute("""
                SELECT product_id, batch_id, SUM(quantity_base) AS qty_base
                FROM stock_in_lines
                WHERE session_id=?
                GROUP BY product_id, batch_id
            """, (session_id,)).fetchall()

            for r in rows:
                conn.execute("""
                    INSERT INTO movements(product_id, batch_id, quantity_base, reason, note)
                    VALUES(?, ?, ?, 'stock_in', ?)
                """, (r["product_id"], r["batch_id"], r["qty_base"], f"session:{session_id}"))

            conn.execute("UPDATE stock_in_sessions SET closed_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))

    def discard_stock_in_session(self, session_id: int):
        """Anulează complet sesiunea (șterge liniile și sesiunea). Nicio mișcare în stoc."""
        conn = connect(self.db_path)
        with conn:
            conn.execute("DELETE FROM stock_in_lines WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM stock_in_sessions WHERE id=?", (session_id,))

    # ---------- REZUMAT SESIUNE ----------
    def get_stock_in_summary(self, session_id: int) -> Dict[str, Any]:
        """
        Returnează totaluri pe produs pentru sesiune (în unitatea umană) + valoare totală (în lei) din unit_cost_cents.
        """
        conn = connect(self.db_path)
        rows = conn.execute("""
            SELECT p.id AS product_id, p.name, p.barcode, p.unit,
                   l.quantity_base, l.unit_cost_cents
            FROM stock_in_lines l
            JOIN products p ON p.id = l.product_id
            WHERE l.session_id=?
        """, (session_id,)).fetchall()

        # agregare în Python pentru controlul conversiilor
        agg: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            pid = r["product_id"]
            unit = r["unit"]
            qty_base = int(r["quantity_base"])
            if unit == 'buc':
                qty_human = qty_base
            else:
                qty_human = qty_base / 1000.0

            value_cents = 0
            if r["unit_cost_cents"] is not None:
                if unit == 'buc':
                    value_cents = r["unit_cost_cents"] * qty_base
                else:
                    # (cents per kg/l) * (ml/g) / 1000
                    value_cents = int(round(r["unit_cost_cents"] * (qty_base / 1000.0)))

            if pid not in agg:
                agg[pid] = {
                    "name": r["name"],
                    "barcode": r["barcode"],
                    "unit": unit,
                    "qty": 0.0 if unit != 'buc' else 0,
                    "value_cents": 0
                }
            agg[pid]["qty"] += qty_human
            agg[pid]["value_cents"] += value_cents

        items = list(agg.values())
        # sortare desc după cantitate
        items.sort(key=lambda x: x["qty"], reverse=True)

        total_distinct = len(items)
        total_qty = sum(x["qty"] for x in items)
        total_value_cents = sum(x["value_cents"] for x in items)

        # pregătește top10 pentru UI
        top10 = [{
            "name": it["name"],
            "barcode": it["barcode"],
            "qty": it["qty"],
            "unit": it["unit"],
            "value_lei": cents_to_lei(it["value_cents"])
        } for it in items[:10]]

        return {
            "total_distinct": total_distinct,
            "total_qty": total_qty,
            "total_value_lei": cents_to_lei(total_value_cents),
            "top10": top10
        }

    # ---------- LISTĂ STOC ----------
    def get_stock_list(self, search: str='') -> List[dict]:
        conn = connect(self.db_path)
        sql = """
        SELECT 
            p.id AS product_id, p.name AS product_name, p.barcode, p.unit,
            COALESCE(v.stock_qty_base, 0) AS stock_qty_base
        FROM products p
        LEFT JOIN current_stock_per_product v ON v.product_id = p.id
        """
        params = ()
        if search:
            like = f"%{search}%"
            sql += " WHERE p.name LIKE ? OR p.barcode LIKE ?"
            params = (like, like)
        sql += " ORDER BY p.name ASC"
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
