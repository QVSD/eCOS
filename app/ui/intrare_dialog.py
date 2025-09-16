from PySide6 import QtWidgets, QtCore, QtGui
from ..services.use_cases import InventoryService

#TO DO cantitatea introdusa nu poate fi cu ,5 trebuie sa fie numar natural!
# Posibilitatea de a modifica datele introduse dupa adaugare in fereastra. In caz ca am pus ceva gresit.
# O optiune de a exporta totul ca si tabel (tot ce adaugasem in sesiunea respectiva)

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
        self.in_barcode.returnPressed.connect(self._prefill_from_barcode)
        self.in_barcode.editingFinished.connect(self._prefill_from_barcode)

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
        
        self.in_unit.currentTextChanged.connect(self._on_unit_changed)
        self._on_unit_changed(self.in_unit.currentText())

        # expirare opțională, activată prin checkbox
        self.chk_has_expiry = QtWidgets.QCheckBox("Are expirare")
        self.in_expiry = QtWidgets.QDateEdit(calendarPopup=True)
        self.in_expiry.setDisplayFormat("yyyy-MM-dd")
        self.in_expiry.setDate(QtCore.QDate.currentDate())
        self.in_expiry.setEnabled(False)
        self.chk_has_expiry.toggled.connect(self.in_expiry.setEnabled)

        self.in_lot = QtWidgets.QLineEdit()
        self.in_lot.setPlaceholderText("Gol = generează automat")
        self.in_lot.setToolTip("Dacă lași gol, sistemul va crea un cod de lot automat (ex. S<ses>-<data>-0001).")


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
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["#", "Denumire", "Cod", "Cant.", "Lot", "Expiră la", "Cost/unit", "Preț", "Valoare"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        # context menu + double click pentru edit
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.doubleClicked.connect(self._edit_selected_line)

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
        self.refresh_lines()          # populeaza tabelul cu liniile reale
        self.refresh_summary()        # doar labelul de sumar


    # ----- helpers -----

    def _format_unit_totals(self, summary: dict) -> str:
        parts = []
        if summary.get("total_qty_buc", 0):
            parts.append(f"{summary['total_qty_buc']} buc")
        if summary.get("total_qty_kg", 0):
            parts.append(f"{summary['total_qty_kg']:.3f} kg")
        if summary.get("total_qty_l", 0):
            parts.append(f"{summary['total_qty_l']:.3f} l")
        return " | ".join(parts) if parts else "0"


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

        # daca produsul exista si pretul introdus difera, actualizeaza pretul la raft
        p = self.svc.find_product_by_barcode(barcode)
        if p:
            old_price = (p["price_per_unit_cents"] / 100.0) if p.get("price_per_unit_cents") is not None else None
            new_price = float(self.in_price.value())
            if old_price is None or abs(new_price - old_price) > 1e-9:
                self.svc.update_product_price(int(p["id"]), new_price)

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

        self.refresh_lines()
        self.refresh_summary()

    def _prefill_from_barcode(self):
        raw = self.in_barcode.text().strip()
        if not raw:
            return
        try:
            code = self._normalize_barcode(raw)
        except Exception:
            return
        p = self.svc.find_product_by_barcode(code)
        if p:
            # pune automat nume/unit/preț curent
            if p.get("name"): self.in_name.setText(p["name"])
            if p.get("unit"): 
                idx = self.in_unit.findText(p["unit"])
                if idx >= 0: self.in_unit.setCurrentIndex(idx)
            if p.get("price_per_unit_cents") is not None:
                self.in_price.setValue(p["price_per_unit_cents"] / 100.0)


    def refresh_lines(self):
        rows = self.svc.get_stock_in_lines(self.session_id)
        self._last_lines = rows   # păstrăm pentru edit
        self.table.setRowCount(0)
        for idx, it in enumerate(rows, start=1):
            r = self.table.rowCount(); self.table.insertRow(r)

            c0 = QtWidgets.QTableWidgetItem(str(idx))
            c0.setData(QtCore.Qt.UserRole, it["line_id"])     # păstrăm line_id
            self.table.setItem(r, 0, c0)

            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(it["name"] or ""))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(it["barcode"] or ""))

            q = it["qty_human"]; unit = it["unit"]
            q_text = f"{int(q)}" if (unit=="buc") else f"{q:.3f}"
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(q_text + f" {unit}"))

            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(it["lot_code"] or ""))
            self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(it["expiry_date"] or ""))
            self.table.setItem(r, 6, QtWidgets.QTableWidgetItem(f"{it['unit_cost_lei']:.2f}"))
            self.table.setItem(r, 7, QtWidgets.QTableWidgetItem(f"{it.get('price_per_unit_lei', 0.0):.2f}")) 
            self.table.setItem(r, 8, QtWidgets.QTableWidgetItem(f"{it['line_value_lei']:.2f}"))


        self.table.resizeColumnsToContents()

    def refresh_summary(self):
        summary = self.svc.get_stock_in_summary(self.session_id)
        qty_text = self._format_unit_totals(summary)
        self.lbl_summary.setText(
            f"Distincte: {summary['total_distinct']}  |  Cantități: {qty_text}  |  Valoare (cost): {summary['total_value_lei']:.2f} lei"
        )


    def finish_session(self):
        self.svc.close_stock_in_session(self.session_id)
        summary = self.svc.get_stock_in_summary(self.session_id)
        qty_text = self._format_unit_totals(summary)
        QtWidgets.QMessageBox.information(
            self,
            "Rezumat intrare",
            "Sesiune închisă.\n\n"
            f"Produse distincte: {summary['total_distinct']}\n"
            f"Cantități: {qty_text}\n"
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
    def _on_unit_changed(self, unit: str):
        if unit == "buc":
            self.in_qty.setDecimals(0)
            self.in_qty.setSingleStep(1)
            self.in_qty.setMinimum(1)
        else:
            self.in_qty.setDecimals(3)
            self.in_qty.setSingleStep(0.1)
            self.in_qty.setMinimum(0.001)
    def _selected_line_id(self) -> int | None:
        r = self.table.currentRow()
        if r < 0: return None
        item0 = self.table.item(r, 0)
        return item0.data(QtCore.Qt.UserRole) if item0 else None

    def _table_menu(self, pos):
        line_id = self._selected_line_id()
        if not line_id:
            return
        menu = QtWidgets.QMenu(self)
        act_edit = menu.addAction("Editează linia…")
        act_del  = menu.addAction("Șterge linia")
        act = menu.exec(self.table.viewport().mapToGlobal(pos))
        if act == act_edit:
            self._edit_selected_line()
        elif act == act_del:
            self._delete_selected_line()

    def _edit_selected_line(self):
        line_id = self._selected_line_id()
        if not line_id: return
        data = next((x for x in getattr(self, "_last_lines", []) if x["line_id"] == line_id), None)
        if not data: return
        dlg = EditStockInLineDialog(self.svc, data, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.refresh_lines()
            self.refresh_summary()

    def _delete_selected_line(self):
        line_id = self._selected_line_id()
        if not line_id: return
        if QtWidgets.QMessageBox.question(self, "Confirmare", "Ștergi această linie?") == QtWidgets.QMessageBox.Yes:
            self.svc.delete_stock_in_line(int(line_id))
            self.refresh_lines()
            self.refresh_summary()

### -----------------------------------------------------------------------------------------------------------------------------------
###     
###                                                     EDIT STOCK 
###     
### -----------------------------------------------------------------------------------------------------------------------------------

class EditStockInLineDialog(QtWidgets.QDialog):
    def __init__(self, svc: InventoryService, line: dict, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.line = line
        self.setWindowTitle(f"Editează – {line['name']}")
        self.resize(420, 300)

        form = QtWidgets.QFormLayout()

        self.lbl_prod = QtWidgets.QLabel(f"{line['name']}  ({line['barcode'] or '—'})")
        form.addRow("Produs", self.lbl_prod)

        self.sp_qty = QtWidgets.QDoubleSpinBox()
        if line["unit"] == "buc":
            self.sp_qty.setDecimals(0); self.sp_qty.setSingleStep(1); self.sp_qty.setMinimum(1)
        else:
            self.sp_qty.setDecimals(3); self.sp_qty.setSingleStep(0.1); self.sp_qty.setMinimum(0.001)
        self.sp_qty.setMaximum(1e9)
        self.sp_qty.setValue(float(line["qty_human"]))
        form.addRow(f"Cantitate ({line['unit']})", self.sp_qty)

        self.chk_exp = QtWidgets.QCheckBox("Are expirare")
        self.dt_exp = QtWidgets.QDateEdit(calendarPopup=True)
        self.dt_exp.setDisplayFormat("yyyy-MM-dd")
        if line["expiry_date"]:
            self.chk_exp.setChecked(True)
            self.dt_exp.setDate(QtCore.QDate.fromString(line["expiry_date"], "yyyy-MM-dd"))
        else:
            self.chk_exp.setChecked(False)
            self.dt_exp.setDate(QtCore.QDate.currentDate())
        self.dt_exp.setEnabled(self.chk_exp.isChecked())
        self.chk_exp.toggled.connect(self.dt_exp.setEnabled)
        w_exp = QtWidgets.QHBoxLayout(); w_exp.addWidget(self.chk_exp); w_exp.addWidget(self.dt_exp)
        ww_exp = QtWidgets.QWidget(); ww_exp.setLayout(w_exp)
        form.addRow("Expirare", ww_exp)

        self.ed_lot = QtWidgets.QLineEdit(line["lot_code"] or "")
        self.ed_lot.setPlaceholderText("Gol = fără lot")
        form.addRow("Lot", self.ed_lot)

        self.sp_cost = QtWidgets.QDoubleSpinBox(); self.sp_cost.setDecimals(2); self.sp_cost.setMaximum(1e9)
        self.sp_cost.setValue(float(line["unit_cost_lei"]))
        form.addRow("Cost / unitate", self.sp_cost)

        self.sp_price = QtWidgets.QDoubleSpinBox()
        self.sp_price.setDecimals(2)
        self.sp_price.setMaximum(1e9)
        self.sp_price.setValue(float(line.get("price_per_unit_lei", 0.0)))
        form.addRow("Preț la raft / unitate", self.sp_price)

        self.ed_sup  = QtWidgets.QLineEdit(line.get("supplier_name") or "")
        self.ed_doc  = QtWidgets.QLineEdit(line.get("supplier_doc") or "")
        form.addRow("Furnizor", self.ed_sup)
        form.addRow("Doc furnizor", self.ed_doc)

        btns = QtWidgets.QHBoxLayout()
        self.btn_ok = QtWidgets.QPushButton("Salvează")
        self.btn_cancel = QtWidgets.QPushButton("Renunță")
        btns.addStretch(); btns.addWidget(self.btn_ok); btns.addWidget(self.btn_cancel)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(form); lay.addLayout(btns)

        self.btn_ok.clicked.connect(self.save)
        self.btn_cancel.clicked.connect(self.reject)

    def save(self):
        try:
            qty = float(self.sp_qty.value())
            exp = self.dt_exp.date().toString("yyyy-MM-dd") if self.chk_exp.isChecked() else None
            lot = (self.ed_lot.text().strip() or None)
            cost = float(self.sp_cost.value())
            sup  = self.ed_sup.text().strip() or None
            doc  = self.ed_doc.text().strip() or None
            shelf_price = float(self.sp_price.value())

            # actualizează prețul din products doar dacă s-a schimbat
            try:
                if abs(shelf_price - float(self.line.get("price_per_unit_lei", 0.0))) > 1e-9:
                    self.svc.update_product_price(int(self.line["product_id"]), shelf_price)
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Atenție", f"Prețul la raft nu a putut fi actualizat: {e}")


            self.svc.update_stock_in_line(
                self.line["line_id"],
                qty_human=qty,
                expiry_date=exp,      # setează/șterge expirarea
                lot_code=lot,         # setează/șterge lotul
                unit_cost_lei=cost,
                supplier_name=sup,
                supplier_doc=doc,
            )
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Eroare", str(e))


