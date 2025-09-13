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
    
    def open_receipt(self) -> int:
        conn = connect(self.db_path)
        with conn:
            cur = conn.execute("INSERT INTO receipts(status) VALUES('open')")
            return cur.lastrowid
    
    def add_line_to_receipt(self, receipt_id: int, barcode: str, qty_human: float) -> int:
        if qty_human <= 0:
            raise ValueError("Cantitatea trebuie să fie > 0.")

        conn = connect(self.db_path)
        with conn:
            st = conn.execute("SELECT status FROM receipts WHERE id=?", (receipt_id,)).fetchone()
            if not st or st["status"] != "open":
                raise ValueError("Bonul nu este în stare 'open'.")

            p = conn.execute(
                "SELECT id, unit, price_per_unit_cents, vat_rate, name FROM products WHERE barcode=?",
                (barcode,)
            ).fetchone()
            if not p:
                raise ValueError("Produs inexistent. Adaugă-l mai întâi (Intrare).")

            qty_base = to_base_qty(p["unit"], qty_human)

            # preț per unitate de bază
            if p["unit"] == "buc":
                unit_price_cents = int(p["price_per_unit_cents"])
            else:
                # preț/kg sau /l → transformăm la preț/gram ori /ml
                unit_price_cents = int(round(p["price_per_unit_cents"] / 1000.0))

            vat_rate = int(p["vat_rate"])

            # Cumulăm dacă există linie cu același produs + același preț/vat (altfel inserăm nouă linie)
            row = conn.execute("""
                SELECT id, qty_base
                FROM receipt_lines
                WHERE receipt_id=? AND product_id=? AND unit_price_cents=? AND vat_rate=?
                ORDER BY id LIMIT 1
            """, (receipt_id, p["id"], unit_price_cents, vat_rate)).fetchone()

            if row:
                new_qty = int(row["qty_base"]) + qty_base
                new_total = new_qty * unit_price_cents
                conn.execute("""
                    UPDATE receipt_lines
                    SET qty_base=?, line_total_cents=?
                    WHERE id=?
                """, (new_qty, new_total, row["id"]))
                line_id = row["id"]
            else:
                line_total = qty_base * unit_price_cents
                cur = conn.execute("""
                    INSERT INTO receipt_lines
                        (receipt_id, product_id, qty_base, unit_price_cents, vat_rate, line_total_cents)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (receipt_id, p["id"], qty_base, unit_price_cents, vat_rate, line_total))
                line_id = cur.lastrowid

        return line_id
    
    def get_receipt(self, receipt_id: int) -> Dict[str, Any]:

        conn = connect(self.db_path)

        head = conn.execute("SELECT * FROM receipts WHERE id=?", (receipt_id,)).fetchone()

        lines = conn.execute("""
            SELECT rl.id, rl.product_id, p.name, p.barcode, p.unit,
                rl.qty_base, rl.unit_price_cents, rl.vat_rate, rl.line_total_cents
            FROM receipt_lines rl
            JOIN products p ON p.id = rl.product_id
            WHERE rl.receipt_id=?
            ORDER BY rl.id
        """, (receipt_id,)).fetchall()

        total_cents = conn.execute("""
            SELECT COALESCE(SUM(line_total_cents),0) AS t
            FROM receipt_lines
            WHERE receipt_id=?
        """, (receipt_id,)).fetchone()["t"]

        return {
            "head": dict(head) if head else None,
            "items": [dict(r) for r in lines],
            "total_cents": int(total_cents),
        }

    def remove_line(self, line_id: int):
        conn = connect(self.db_path)
        with conn:
            conn.execute("DELETE FROM receipt_lines WHERE id=?", (line_id,))

    # ---------- FIFO pe lot la finalizare ----------
    def _available_batches(self, conn, product_id: int) -> List[Dict]:
        # loturi cu stoc > 0, ordonate: cele cu expirare (cea mai apropiată) → apoi fără expirare
        rows = conn.execute("""
            SELECT b.id AS batch_id, b.expiry_date,
                   COALESCE(SUM(m.quantity_base),0) AS stock_base
            FROM batches b
            LEFT JOIN movements m ON m.batch_id = b.id
            WHERE b.product_id=?
            GROUP BY b.id
            HAVING stock_base > 0
            ORDER BY (b.expiry_date IS NULL), b.expiry_date ASC, b.id ASC
        """, (product_id,)).fetchall()
        return [dict(r) for r in rows]

    def _consume_fifo(self, conn, product_id: int, need_base: int, note: str):
        remaining = need_base
        for r in self._available_batches(conn, product_id):
            take = min(remaining, int(r["stock_base"]))
            if take > 0:
                conn.execute("""
                    INSERT INTO movements(product_id, batch_id, quantity_base, reason, note)
                    VALUES(?, ?, ?, 'sale', ?)
                """, (product_id, r["batch_id"], -take, note))
                remaining -= take
            if remaining == 0:
                break
        if remaining > 0:
            # dacă vrei să permiți consum și din "fără loturi", scoate comentariul de mai jos
            # conn.execute("INSERT INTO movements(product_id, batch_id, quantity_base, reason, note) VALUES(?, NULL, ?, 'sale', ?)", (product_id, -remaining, note))
            # remaining = 0
            raise ValueError("Stoc insuficient pentru produs.")
        
    def finalize_receipt(self, receipt_id: int):
        conn = connect(self.db_path)
        with conn:
            head = conn.execute("SELECT status FROM receipts WHERE id=?", (receipt_id,)).fetchone()
            if not head:
                raise ValueError("Bon inexistent.")
            if head["status"] != "open":
                raise ValueError("Bonul nu este în stare 'open'.")

            # luăm liniile bonului
            items = conn.execute("""
                SELECT product_id, qty_base
                FROM receipt_lines
                WHERE receipt_id=?
                ORDER BY id
            """, (receipt_id,)).fetchall()

            # pentru fiecare produs, consumăm FIFO pe lot
            for it in items:
                product_id = int(it["product_id"])
                remaining  = int(it["qty_base"])

                # 1) loturi cu stoc > 0, ordonate: expirare apropiată → NULL la final
                rows = conn.execute("""
                    SELECT b.id AS batch_id,
                        COALESCE(SUM(m.quantity_base),0) AS stock_base,
                        b.expiry_date
                    FROM batches b
                    LEFT JOIN movements m ON m.batch_id = b.id
                    WHERE b.product_id=?
                    GROUP BY b.id
                    HAVING stock_base > 0
                    ORDER BY (b.expiry_date IS NULL), b.expiry_date ASC, b.id ASC
                """, (product_id,)).fetchall()

                for r in rows:
                    if remaining <= 0:
                        break
                    take = min(remaining, int(r["stock_base"]))
                    if take > 0:
                        conn.execute("""
                            INSERT INTO movements(product_id, batch_id, quantity_base, reason, note)
                            VALUES (?, ?, ?, 'sale', ?)
                        """, (product_id, r["batch_id"], -take, f"receipt:{receipt_id}"))
                        remaining -= take

                # 2) fallback: stoc fără lot (batch_id IS NULL)
                if remaining > 0:
                    s_null = conn.execute("""
                        SELECT COALESCE(SUM(quantity_base),0) AS stock_base
                        FROM movements
                        WHERE product_id=? AND batch_id IS NULL
                    """, (product_id,)).fetchone()["stock_base"]
                    s_null = int(s_null)
                    if s_null >= remaining:
                        conn.execute("""
                            INSERT INTO movements(product_id, batch_id, quantity_base, reason, note)
                            VALUES (?, NULL, ?, 'sale', ?)
                        """, (product_id, -remaining, f"receipt:{receipt_id}"))
                        remaining = 0

                if remaining > 0:
                    raise ValueError("Stoc insuficient pentru unul dintre produse.")

            # total din SUM(line_total_cents)
            total_cents = conn.execute("""
                SELECT COALESCE(SUM(line_total_cents),0) AS t
                FROM receipt_lines
                WHERE receipt_id=?
            """, (receipt_id,)).fetchone()["t"]

            conn.execute("""
                UPDATE receipts
                SET status='closed', closed_at=CURRENT_TIMESTAMP, total_cached_cents=?
                WHERE id=?
            """, (int(total_cents), receipt_id))

    def void_receipt(self, receipt_id: int):
        conn = connect(self.db_path)
        with conn:
            conn.execute("UPDATE receipts SET status='void' WHERE id=? AND status='open'", (receipt_id,))
            conn.execute("DELETE FROM receipt_lines WHERE receipt_id=?", (receipt_id,))

        # ---- conversii bază -> uman (pt. afișare) ----
    def from_base_qty(self, unit: str, qty_base: int) -> float:
        if unit == "buc":
            return float(qty_base)
        if unit in ("kg", "l"):
            return qty_base / 1000.0
        raise ValueError("Unitate necunoscută")

    # ---- listare stoc pe produs (cu filtrare) ----
    def get_stock_products(self, search: str = "", low_only: bool = False, low_threshold_human: float = 0.0) -> list[dict]:
        conn = connect(self.db_path)
        rows = conn.execute("""
        SELECT p.id AS product_id, p.name, p.barcode, p.unit,
                COALESCE(SUM(m.quantity_base),0) AS stock_base
        FROM products p
        LEFT JOIN movements m ON m.product_id = p.id
        GROUP BY p.id
        """).fetchall()

        items = []
        for r in rows:
            unit = r["unit"]
            stock_base = int(r["stock_base"] or 0)
            stock_human = float(stock_base) if unit == "buc" else stock_base / 1000.0
            items.append({
                "product_id": r["product_id"],
                "name": r["name"],
                "barcode": r["barcode"],
                "unit": unit,
                "stock_base": stock_base,
                "stock_human": stock_human,
            })

        # căutare
        if search:
            s = search.lower()
            items = [it for it in items if s in (it["name"] or "").lower() or s in (it["barcode"] or "").lower()]

        # stoc scăzut per unitatea produsului
        if low_only:
            def thr_base_for(unit: str) -> int:
                return int(round(low_threshold_human)) if unit == "buc" else int(round(low_threshold_human * 1000))
            items = [it for it in items if it["stock_base"] <= thr_base_for(it["unit"])]

        items.sort(key=lambda x: x["name"] or "")
        return items


    def get_product_batches(self, product_id: int) -> list[dict]:
        conn = connect(self.db_path)
        rows = conn.execute("""
        SELECT b.id AS batch_id, b.expiry_date,
                COALESCE(SUM(m.quantity_base),0) AS stock_base,
                p.unit
        FROM batches b
        JOIN products p ON p.id = b.product_id
        LEFT JOIN movements m ON m.batch_id = b.id
        WHERE b.product_id=?
        GROUP BY b.id
        HAVING stock_base <> 0
        ORDER BY (b.expiry_date IS NULL), b.expiry_date ASC, b.id ASC
        """, (product_id,)).fetchall()

        items = []
        unit = None
        for r in rows:
            unit = r["unit"]
            stock_base = int(r["stock_base"] or 0)
            items.append({
                "batch_id": r["batch_id"],
                "expiry_date": r["expiry_date"],
                "stock_base": stock_base,
                "stock_human": self.from_base_qty(r["unit"], stock_base),
                "label": r["expiry_date"] or "(fără expirare)",
            })

        # pseudo-lot pentru batch_id IS NULL
        null_row = conn.execute("""
            SELECT COALESCE(SUM(quantity_base),0) AS stock_base
            FROM movements
            WHERE product_id=? AND batch_id IS NULL
        """, (product_id,)).fetchone()
        null_stock = int(null_row["stock_base"] or 0)
        if null_stock != 0:
            if unit is None:
                unit = conn.execute("SELECT unit FROM products WHERE id=?", (product_id,)).fetchone()["unit"]
            items.append({
                "batch_id": None,
                "expiry_date": None,
                "stock_base": null_stock,
                "stock_human": self.from_base_qty(unit, null_stock),
                "label": "(fără lot)",
            })

        return items

