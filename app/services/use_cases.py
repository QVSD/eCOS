from typing import Optional, List, Dict, Any
from ..infra.db import connect
from datetime import date, datetime 

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

def _date_text(v):
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
    # e deja string
    return str(v)

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
            if lot_code:
                row = conn.execute(
                    "SELECT id, expiry_date FROM batches WHERE product_id=? AND lot_code=?",
                    (product_id, lot_code)
                ).fetchone()
                if row:
                    old_txt = _date_text(row["expiry_date"])
                    new_txt = _date_text(expiry_date)
                    # Dacă vine o dată diferită -> actualizează lotul
                    if new_txt and old_txt != new_txt:
                        conn.execute("UPDATE batches SET expiry_date=? WHERE id=?", (new_txt, row["id"]))
                    return row["id"]

            row = conn.execute(
                "SELECT id FROM batches WHERE product_id=? AND IFNULL(expiry_date,'')=IFNULL(?, '') AND IFNULL(lot_code,'')=IFNULL(?, '')",
                (product_id, _date_text(expiry_date) or None, lot_code or None)
            ).fetchone()
            if row:
                return row["id"]

            cur = conn.execute(
                "INSERT INTO batches(product_id, expiry_date, lot_code) VALUES(?,?,?)",
                (product_id, _date_text(expiry_date) or None, lot_code or None)
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

            # lot (opțional) – dacă nu s-a introdus, îl generăm automat
            if not lot_code:
                lot_code = self._auto_lot_code(session_id)

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
        conn = connect(self.db_path)
        rows = conn.execute("""
            SELECT p.id AS product_id, p.name, p.barcode, p.unit,
                l.quantity_base, l.unit_cost_cents
            FROM stock_in_lines l
            JOIN products p ON p.id = l.product_id
            WHERE l.session_id=?
        """, (session_id,)).fetchall()

        agg: Dict[int, Dict[str, Any]] = {}
        # --- NOI: totaluri pe fiecare unitate
        total_buc = 0            # int
        total_kg  = 0.0          # float (kg)
        total_l   = 0.0          # float (l)

        for r in rows:
            pid  = r["product_id"]
            unit = r["unit"]
            qty_base = int(r["quantity_base"])

            if unit == "buc":
                qty_human = qty_base
                total_buc += qty_base
            elif unit == "kg":
                qty_human = qty_base / 1000.0
                total_kg  += qty_human
            elif unit == "l":
                qty_human = qty_base / 1000.0
                total_l   += qty_human
            else:
                raise ValueError(f"Unitate necunoscută: {unit}")

            value_cents = 0
            if r["unit_cost_cents"] is not None:
                if unit == "buc":
                    value_cents = r["unit_cost_cents"] * qty_base
                else:
                    value_cents = int(round(r["unit_cost_cents"] * (qty_base / 1000.0)))

            if pid not in agg:
                agg[pid] = {"name": r["name"], "barcode": r["barcode"], "unit": unit,
                            "qty": 0.0 if unit != "buc" else 0, "value_cents": 0}
            agg[pid]["qty"] += qty_human
            agg[pid]["value_cents"] += value_cents

        items = list(agg.values())
        items.sort(key=lambda x: x["qty"], reverse=True)

        total_distinct = len(items)
        total_value_cents = sum(x["value_cents"] for x in items)

        top10 = [{
            "name": it["name"], "barcode": it["barcode"], "qty": it["qty"],
            "unit": it["unit"], "value_lei": cents_to_lei(it["value_cents"])
        } for it in items[:10]]

        return {
            "total_distinct": total_distinct,
            # păstrăm 'total_qty' DOAR pentru compatibilitate, dar nu-l mai folosim în UI
            "total_qty": float(total_buc) + total_kg + total_l,
            "total_qty_buc": int(total_buc),
            "total_qty_kg":  float(total_kg),
            "total_qty_l":   float(total_l),
            "total_value_lei": cents_to_lei(total_value_cents),
            "top10": top10,
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
        SELECT b.id AS batch_id,  b.lot_code, b.expiry_date,
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
                "lot_code": r["lot_code"],  
                "stock_base": stock_base,
                "stock_human": self.from_base_qty(r["unit"], stock_base),
            })

        # pseudo-lot pentru batch_id IS NULL
        null_stock = int(conn.execute("""
                SELECT COALESCE(SUM(quantity_base),0) AS stock_base
                FROM movements
                WHERE product_id=? AND batch_id IS NULL
            """, (product_id,)).fetchone()["stock_base"] or 0)

        if null_stock != 0:
            if unit is None:
                unit = conn.execute("SELECT unit FROM products WHERE id=?", (product_id,)).fetchone()["unit"]
            items.append({
                "batch_id": None,
                "lot_code": None,
                "expiry_date": None,
                "stock_base": null_stock,
                "stock_human": self.from_base_qty(unit, null_stock),
            })

        return items

    def get_expiring_batches(self, days: int) -> list[dict]:
        """
        Loturi care expiră în următoarele `days` zile (inclusiv azi), doar cu stoc > 0.
        Returnează: product_name, barcode, expiry_date (YYYY-MM-DD), stock_human, days_left
        """
        conn = connect(self.db_path)
        rows = conn.execute("""
            SELECT p.name AS product_name, p.barcode, p.unit, b.expiry_date,
                COALESCE(SUM(m.quantity_base),0) AS stock_base
            FROM batches b
            JOIN products p ON p.id = b.product_id
            LEFT JOIN movements m ON m.batch_id = b.id
            WHERE b.expiry_date IS NOT NULL
            GROUP BY b.id
            HAVING stock_base > 0
            ORDER BY b.expiry_date ASC, b.id ASC
        """).fetchall()

        today = date.today()
        items = []

        for r in rows:
            raw = r["expiry_date"]

            # normalizează la datetime.date
            if isinstance(raw, datetime):
                d = raw.date()
            elif isinstance(raw, date):
                d = raw
            elif isinstance(raw, str) and raw:
                try:
                    d = date.fromisoformat(raw)
                except ValueError:
                    continue
            else:
                continue

            days_left = (d - today).days
            if 0 <= days_left <= int(days):
                stock_base = int(r["stock_base"] or 0)
                stock_human = self.from_base_qty(r["unit"], stock_base)
                items.append({
                    "product_name": r["product_name"],
                    "barcode": r["barcode"],
                    "expiry_date": d.isoformat(),   # UI primește mereu text
                    "stock_human": stock_human,
                    "days_left": days_left,
                })

        items.sort(key=lambda x: (x["days_left"], x["expiry_date"]))
        return items
    
    def update_product_price(self, product_id: int, price_per_unit_lei: float) -> None:
        conn = connect(self.db_path)
        with conn:
            conn.execute(
                "UPDATE products SET price_per_unit_cents=? WHERE id=?",
                (lei_to_cents(price_per_unit_lei), int(product_id))
            )

    
    def _next_seq(self, name: str) -> int:
        ### Contor atomic pe cheie (ex: 'lot:session:15:20250919').
        conn = connect(self.db_path)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sequences (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
            """)
            conn.execute("INSERT OR IGNORE INTO sequences(name, value) VALUES(?, 0)", (name,))
            conn.execute("UPDATE sequences SET value = value + 1 WHERE name=?", (name,))
            row = conn.execute("SELECT value FROM sequences WHERE name=?", (name,)).fetchone()
            return int(row["value"])

    def _auto_lot_code(self, session_id: int) -> str:
        """Generează un cod de lot lizibil și unic. Format: S<sess>-<zi>-<nr> (ex. S12-20250919-0001)."""
        ymd = date.today().strftime("%Y%m%d")
        seq = self._next_seq(f"lot:session:{session_id}:{ymd}")   # contor pe sesiune + zi
        return f"S{session_id}-{ymd}-{seq:04d}"
    
    # --- Liniile dintr-o sesiune de intrare (pt. UI) ---
    def get_stock_in_lines(self, session_id: int) -> list[dict]:
        """
        Returnează liniile exacte din sesiune:
        line_id, product_id, name, barcode, unit, qty_human, expiry_date, lot_code,
        unit_cost_lei, line_value_lei
        """
        conn = connect(self.db_path)
        rows = conn.execute("""
            SELECT l.id AS line_id, l.product_id, l.quantity_base, l.unit_cost_cents,
                l.supplier_name, l.supplier_doc,
                p.name, p.barcode, p.unit, p.price_per_unit_cents,
                b.expiry_date, b.lot_code
            FROM stock_in_lines l
            JOIN products p ON p.id = l.product_id
            LEFT JOIN batches b ON b.id = l.batch_id
            WHERE l.session_id=?
            ORDER BY l.id
        """, (session_id,)).fetchall()

        items = []
        for r in rows:
            unit = r["unit"]
            qty_base = int(r["quantity_base"])
            qty_human = float(qty_base) if unit == "buc" else qty_base / 1000.0
            cost_cents = r["unit_cost_cents"]
            # valoarea liniei, conform convenției (cost per buc / kg / l)
            if cost_cents is None:
                line_val_lei = 0.0
            else:
                if unit == "buc":
                    line_val_lei = (cost_cents * qty_human) / 100.0
                else:
                    line_val_lei = (cost_cents * (qty_base / 1000.0)) / 100.0

            items.append({
                "line_id": int(r["line_id"]),
                "product_id": int(r["product_id"]),
                "name": r["name"],
                "barcode": r["barcode"],
                "unit": unit,
                "qty_human": qty_human,
                "expiry_date": (
                    r["expiry_date"].isoformat() if hasattr(r["expiry_date"], "isoformat")
                    else (str(r["expiry_date"]) if r["expiry_date"] is not None else None)
                ),
                "lot_code": r["lot_code"],
                "unit_cost_lei": 0.0 if cost_cents is None else cost_cents / 100.0,
                "line_value_lei": line_val_lei,
                "supplier_name": r["supplier_name"],
                "supplier_doc": r["supplier_doc"],
                "price_per_unit_lei": 0.0 if r["price_per_unit_cents"] is None else r["price_per_unit_cents"] / 100.0,
            })
        return items

    def update_stock_in_line(
        self,
        line_id: int,
        *,
        qty_human: float | None = None,
        expiry_date: str | None | object = ...,
        lot_code: str | None | object = ...,
        unit_cost_lei: float | None = None,
        supplier_name: str | None | object = ...,
        supplier_doc: str | None | object = ...,
    ) -> None:
        conn = connect(self.db_path)
        row = conn.execute("""
            SELECT l.product_id, l.quantity_base, l.unit_cost_cents, l.batch_id,
                p.unit, l.supplier_name, l.supplier_doc
            FROM stock_in_lines l
            JOIN products p ON p.id = l.product_id
            WHERE l.id=?
        """, (line_id,)).fetchone()
        if not row:
            raise ValueError("Linia nu există.")

        product_id = int(row["product_id"])
        unit = row["unit"]

        # cantitate -> base
        new_qty_base = int(row["quantity_base"])
        if qty_human is not None:
            new_qty_base = int(round(qty_human)) if unit == "buc" else int(round(float(qty_human) * 1000))

        # cost
        new_cost_cents = row["unit_cost_cents"]
        if unit_cost_lei is not None:
            new_cost_cents = lei_to_cents(unit_cost_lei)

        # batch (schimbă doar dacă a cerut UI)
        new_batch_id = row["batch_id"]
        if (expiry_date is not ...) or (lot_code is not ...):
            exp = None if expiry_date is ... else expiry_date
            lot = None if lot_code is ... else (lot_code or None)
            new_batch_id = self.get_or_create_batch(product_id, exp, lot)

        # supplier fields (păstrează-vechile dacă nu-s transmise)
        new_supplier_name = row["supplier_name"] if supplier_name is ... else supplier_name
        new_supplier_doc  = row["supplier_doc"]  if supplier_doc  is ... else supplier_doc

        with conn:
            conn.execute("""
                UPDATE stock_in_lines
                SET quantity_base=?,
                    unit_cost_cents=?,
                    batch_id=?,
                    supplier_name=?,
                    supplier_doc=?
                WHERE id=?
            """, (new_qty_base, new_cost_cents, new_batch_id, new_supplier_name, new_supplier_doc, line_id))

    def delete_stock_in_line(self, line_id: int) -> None:
        conn = connect(self.db_path)
        with conn:
            conn.execute("DELETE FROM stock_in_lines WHERE id=?", (line_id,))


