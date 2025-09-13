from PySide6 import QtWidgets, QtCore, QtGui
from ..services.use_cases import InventoryService

#TO DO cantitatea introdusa nu poate fi cu ,5 trebuie sa fie numar natural!

class IntrareDialog(QtWidgets.QDialog):
    def __init__(self, svc: InventoryService, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.setWindowTitle("Intrare în stoc (Sesiune)")
        self.resize(760, 560)

        # 1) Pornește o sesiune nouă
        self.session_id = self.svc.start_stock_in_session()

        # 2) Formularele de introducere
        form = QtWidgets.QFormLayout()

        self.in_barcode = QtWidgets.QLineEdit()
        self.in_barcode.setPlaceholderText("Scaneaza sau introdu codul de bare")
        rx = QtCore.QRegularExpression(r"^\d{0,13}$")
        self.in_barcode.setValidator(QtGui.QRegularExpressionValidator(rx))
        self.in_barcode.setMaxLength(13)

        self.in_name = QtWidgets.QLineEdit()
        self.in_name.setPlaceholderText("Denumire produs (dacă e nou)")

        self.in_unit = QtWidgets.QComboBox()
        self.in_unit.addItems(["buc", "kg", "l"])

        self.in_price = QtWidgets.QDoubleSpinBox()
        self.in_price.setRange(0, 1_000_000)
        self.in_price.setDecimals(2)
        self.in_price.setSuffix(" lei")

        self.in_qty = QtWidgets.QDoubleSpinBox()
        self.in_qty.setRange(0.001, 1_000_000)
        self.in_qty.setDecimals(3)
        self.in_qty.setValue(1.000)

        # expirare opțională, activată prin checkbox
        self.chk_has_expiry = QtWidgets.QCheckBox("Are expirare")
        self.in_expiry = QtWidgets.QDateEdit(calendarPopup=True)
        self.in_expiry.setDisplayFormat("yyyy-MM-dd")
        self.in_expiry.setDate(QtCore.QDate.currentDate())
        self.in_expiry.setEnabled(False)
        self.chk_has_expiry.toggled.connect(self.in_expiry.setEnabled)

        self.in_lot = QtWidgets.QLineEdit()
        self.in_lot.setPlaceholderText("Cod lot (opțional)")

        self.in_cost = QtWidgets.QDoubleSpinBox()
        self.in_cost.setRange(0, 1_000_000)
        self.in_cost.setDecimals(2)
        self.in_cost.setSuffix(" lei")
        self.in_supplier = QtWidgets.QLineEdit()
        self.in_supplier.setPlaceholderText("Furnizor (opțional)")
        self.in_doc = QtWidgets.QLineEdit()
        self.in_doc.setPlaceholderText("Document furnizor (opțional)")

        form.addRow("Cod de bare", self.in_barcode)
        form.addRow("Denumire (dacă e nou)", self.in_name)
        form.addRow("Unitate", self.in_unit)
        form.addRow("Preț / unitate", self.in_price)
        form.addRow("Cantitate", self.in_qty)
        h_exp = QtWidgets.QHBoxLayout()
        h_exp.addWidget(self.chk_has_expiry)
        h_exp.addWidget(self.in_expiry)
        w_exp = QtWidgets.QWidget()
        w_exp.setLayout(h_exp)
        form.addRow("Expirare", w_exp)
        form.addRow("Lot", self.in_lot)
        form.addRow("Cost / unitate (opțional)", self.in_cost)
        form.addRow("Furnizor (opțional)", self.in_supplier)
        form.addRow("Doc furnizor (opțional)", self.in_doc)

        # 3) Butoane acțiune
        self.btn_add = QtWidgets.QPushButton("Adaugă în sesiune (Enter)")
        self.btn_close = QtWidgets.QPushButton("Închide sesiunea")
        self.btn_cancel = QtWidgets.QPushButton("Anulează")

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.btn_add)
        btns.addStretch()
        btns.addWidget(self.btn_close)
        btns.addWidget(self.btn_cancel)

        # 4) Tabel + rezumat
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Denumire", "Cod", "Cant.", "Valoare (lei)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self.lbl_summary = QtWidgets.QLabel("—")
        self.lbl_summary.setStyleSheet("font-weight: 600;")

        # 5) Layout general
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(btns)
        layout.addWidget(self.table)
        layout.addWidget(self.lbl_summary)

        # 6) Conexiuni
        self.btn_add.clicked.connect(self.add_line)
        self.btn_close.clicked.connect(self.finish_session)
        self.btn_cancel.clicked.connect(self.reject)

        # Shortcuts (QtGui!)
        QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self.add_line)
        QtGui.QShortcut(QtGui.QKeySequence("Enter"),  self, activated=self.add_line)
        QtGui.QShortcut(QtGui.QKeySequence("Esc"),    self, activated=self.reject)

        self.in_barcode.setFocus()
        self.refresh_summary()

    # ----- helpers -----
    def _expiry_str(self) -> str | None:
        return self.in_expiry.date().toString("yyyy-MM-dd") if self.chk_has_expiry.isChecked() else None

    def _fmt_qty(self, qty: float, unit: str) -> str:
        if unit == "buc":
            return f"{int(round(qty))} buc"
        else:
            return f"{qty:.3f} {unit}"

    # ----- acțiuni -----
    def add_line(self):
        raw = self.in_barcode.text().strip()
        if not raw:
            QtWidgets.QMessageBox.warning(self, "Eroare", "Scanează sau introdu un cod de bare.")
            self.in_barcode.setFocus()
            return

        # VALIDARE cod de bare (aruncă mesaj și oprește dacă e invalid)
        try:
            barcode = self._normalize_barcode(raw)
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Cod de bare invalid", str(e))
            self.in_barcode.setFocus()
            self.in_barcode.selectAll()
            return

        qty = float(self.in_qty.value())
        if qty <= 0:
            QtWidgets.QMessageBox.warning(self, "Eroare", "Cantitatea trebuie să fie > 0.")
            return

        self.svc.add_stock_in_line(
            session_id=self.session_id,
            barcode=barcode,
            quantity=qty,
            product_name=(self.in_name.text().strip() or None),
            unit=self.in_unit.currentText(),
            price_per_unit_lei=float(self.in_price.value()),
            expiry_date=(self.in_expiry.date().toString("yyyy-MM-dd") if self.chk_has_expiry.isChecked() else None),
            lot_code=(self.in_lot.text().strip() or None),
            unit_cost_lei=(float(self.in_cost.value()) if self.in_cost.value() > 0 else None),
            supplier_name=(self.in_supplier.text().strip() or None),
            supplier_doc=(self.in_doc.text().strip() or None),
        )

        # reset pentru următoarea scanare
        self.in_barcode.clear()
        self.in_name.clear()
        self.in_lot.clear()
        self.in_qty.setValue(1.000)
        self.in_barcode.setFocus()

        self.refresh_summary()

    def refresh_summary(self):
        summary = self.svc.get_stock_in_summary(self.session_id)
        items = summary["top10"]

        # tabel
        self.table.setRowCount(0)
        for it in items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(it["name"]))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(it["barcode"] or ""))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(self._fmt_qty(it["qty"], it["unit"])))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(f"{it['value_lei']:.2f}"))

        # rezumat
        self.lbl_summary.setText(
            f"Distincte: {summary['total_distinct']}  |  Cantitate totală: {summary['total_qty']:.3f}  |  Valoare (cost): {summary['total_value_lei']:.2f} lei"
        )

    def finish_session(self):
        # scrie mișcările în stoc și închide sesiunea
        self.svc.close_stock_in_session(self.session_id)
        summary = self.svc.get_stock_in_summary(self.session_id)
        QtWidgets.QMessageBox.information(
            self,
            "Rezumat intrare",
            "Sesiune închisă.\n\n"
            f"Produse distincte: {summary['total_distinct']}\n"
            f"Cantitate totală: {summary['total_qty']:.3f}\n"
            f"Valoare (cost): {summary['total_value_lei']:.2f} lei\n"
        )
        self.accept()

    def reject(self):
        # Anulează sesiunea: șterge linii + sesiunea; NU afectează stocul
        self.svc.discard_stock_in_session(self.session_id)
        super().reject()
    def _ean13_check_digit(self, body12: str) -> int:
        if len(body12) != 12 or not body12.isdigit():
            raise ValueError("EAN-13 trebuie să aibă 12 cifre + cifră de control.")
        s_odd  = sum(int(d) for i, d in enumerate(body12, 1) if i % 2 == 1)   # 1,3,5,...
        s_even = sum(int(d) for i, d in enumerate(body12, 1) if i % 2 == 0)   # 2,4,6,...
        total = s_odd + 3 * s_even
        return (10 - (total % 10)) % 10

    def _ean8_check_digit(self, body7: str) -> int:
        if len(body7) != 7 or not body7.isdigit():
            raise ValueError("EAN-8 trebuie să aibă 7 cifre + cifră de control.")
        s_odd  = int(body7[0]) + int(body7[2]) + int(body7[4]) + int(body7[6])
        s_even = int(body7[1]) + int(body7[3]) + int(body7[5])
        total = 3 * s_odd + s_even
        return (10 - (total % 10)) % 10

    def _upca_check_digit(self, body11: str) -> int:
        if len(body11) != 11 or not body11.isdigit():
            raise ValueError("UPC-A trebuie să aibă 11 cifre + cifră de control.")
        s_odd  = sum(int(d) for i, d in enumerate(body11, 1) if i % 2 == 1)   # 1,3,5,7,9,11
        s_even = sum(int(d) for i, d in enumerate(body11, 1) if i % 2 == 0)   # 2,4,6,8,10
        total = 3 * s_odd + s_even
        return (10 - (total % 10)) % 10

    def _normalize_barcode(self, raw: str) -> str:
        """Returnează EAN normalizat (string) sau ridică ValueError cu mesaj explicit."""
        code = raw.strip()
        if not code.isdigit():
            raise ValueError("Codul de bare trebuie să conțină doar cifre.")
        if len(set(code)) == 1:
            raise ValueError("Cod invalid (toate cifrele identice).")

        # EAN-13
        if len(code) == 13:
            body, cd = code[:12], int(code[12])
            if self._ean13_check_digit(body) != cd:
                raise ValueError("EAN-13 invalid (cifra de control nu corespunde).")
            return code

        # EAN-8
        if len(code) == 8:
            body, cd = code[:7], int(code[7])
            if self._ean8_check_digit(body) != cd:
                raise ValueError("EAN-8 invalid (cifra de control nu corespunde).")
            return code

        # UPC-A (12) -> normalizează la EAN-13 (prefix 0)
        if len(code) == 12:
            body, cd = code[:11], int(code[11])
            if self._upca_check_digit(body) != cd:
                raise ValueError("UPC-A invalid (cifra de control nu corespunde).")
            ean13 = "0" + code  # conversie standard UPC-A -> EAN-13
            # (opțional) verifică și ca EAN-13:
            if self._ean13_check_digit(ean13[:12]) != int(ean13[12]):
                raise ValueError("Cod valid UPC-A, dar conversia la EAN-13 a eșuat.")
            return ean13

        raise ValueError("Lungime cod invalidă (accept: 8, 12 sau 13 cifre).")

