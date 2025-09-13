from typing import List, Dict, Any, Optional
from ..infra.db import connect

class InventoryService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # --- EXISTENT, dar recomand să-l ajustezi la noul view (stock_qty_base + unit) ---
    def get_stock_list(self, search: str = '') -> List[Dict[str, Any]]:
        conn = connect(self.db_path)
        sql = """
        SELECT 
            p.id AS product_id,
            p.name AS product_name,
            p.barcode AS barcode,
            p.unit AS unit,
            COALESCE(v.stock_qty_base, 0) AS stock_qty_base
        FROM products p
        LEFT JOIN current_stock_per_product v ON v.product_id = p.id
        """
        params: tuple = ()
        if search:
            like = f"%{search}%"
            sql += " WHERE p.name LIKE ? OR p.barcode LIKE ?"
            params = (like, like)
        sql += " ORDER BY p.name ASC"
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    # =========================
    #   SEQUENCES + EAN-13
    # =========================

    def _next_sequence(self, name: str) -> int:
        """
        Întoarce următoarea valoare pentru 'name' din tabela `sequences`
        într-o tranzacție (atomic). Dacă nu există rândul, îl creează cu 1.
        """
        conn = connect(self.db_path)
        with conn:  # tranzacție
            cur = conn.execute(
                "UPDATE sequences SET value = value + 1 WHERE name = ?",
                (name,)
            )
            if cur.rowcount == 0:  # nu există încă secvența
                conn.execute(
                    "INSERT INTO sequences(name, value) VALUES (?, 1)",
                    (name,)
                )
                return 1
            row = conn.execute(
                "SELECT value FROM sequences WHERE name = ?",
                (name,)
            ).fetchone()
            return int(row["value"])

    @staticmethod
    def _ean13_check_digit(d12: str) -> int:
        """
        Calculează cifra de control EAN-13 pentru primele 12 cifre.
        Algoritm: (sum(odd) + 3*sum(even)) % 10 => check = (10 - mod) % 10
        """
        if len(d12) != 12 or not d12.isdigit():
            raise ValueError("Trebuie exact 12 cifre pentru EAN-13 (fără check digit).")
        total = 0
        for i, ch in enumerate(d12, start=1):
            n = int(ch)
            total += n * (3 if (i % 2 == 2 % 2) else 1)  # echivalent: 3 pentru poziții pare
        return (10 - (total % 10)) % 10

    def generate_internal_ean13(self, prefix: str = "290") -> str:
        """
        Generează un EAN-13 intern:
        - prefix (ex. '290' pentru coduri interne)
        - număr secvențial zero-padded ca să ajungi la 12 cifre
        - calculează cifra de control (a 13-a cifră)
        """
        seq = self._next_sequence("ean_internal")
        body = f"{prefix}{seq:0{12 - len(prefix)}d}"  # 12 cifre fără check digit
        if len(body) != 12:
            raise ValueError("Prefixul + secvența depășesc 12 cifre. Ajustează prefixul.")
        cd = self._ean13_check_digit(body)
        return body + str(cd)

    def assign_barcode_if_missing(self, product_id: int, prefix: str = "290") -> str:
        """
        Dacă produsul nu are barcode, generează unul intern și îl salvează.
        Returnează barcode-ul (existent sau nou).
        """
        conn = connect(self.db_path)
        with conn:
            row = conn.execute(
                "SELECT barcode FROM products WHERE id = ?",
                (product_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Produsul nu există.")
            if row["barcode"]:
                return row["barcode"]

            ean = self.generate_internal_ean13(prefix=prefix)
            conn.execute(
                "UPDATE products SET barcode = ?, updated_at = CURRENT_TIMESTAMP, version = version + 1 WHERE id = ?",
                (ean, product_id)
            )
            return ean
