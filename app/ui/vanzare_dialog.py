from PySide6 import QtWidgets, QtCore, QtGui
from ..services.use_cases import InventoryService
from ..util.barcode import normalize_barcode  # ← validarea EAN/UPC

class VanzareDialog(QtWidgets.QDialog):
    def __init__(self, svc: InventoryService, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.setWindowTitle("Vânzare / Bon intern")
        self.resize(800, 600)

        self.receipt_id = self.svc.open_receipt()

        # ---- controale ----
        form = QtWidgets.QHBoxLayout()
        self.in_barcode = QtWidgets.QLineEdit()
        self.in_barcode.setPlaceholderText("Scanează codul...")
        self.in_qty = QtWidgets.QDoubleSpinBox()
        self.in_qty.setDecimals(3)
        self.in_qty.setValue(1.000)
        self.in_qty.setMaximum(1e6)
        self.btn_add = QtWidgets.QPushButton("Adaugă (Enter)")
        form.addWidget(QtWidgets.QLabel("Cod"))
        form.addWidget(self.in_barcode, 2)
        form.addWidget(QtWidgets.QLabel("Cant."))
        form.addWidget(self.in_qty, 1)
        form.addWidget(self.btn_add)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Denumire", "Cod", "Cant.", "Subtotal"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        # meniu contextual + Del
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        QtGui.QShortcut(QtGui.QKeySequence("Del"), self, activated=self.remove_selected_line)

        self.lbl_total = QtWidgets.QLabel("Total: 0,00 lei")
        f = self.lbl_total.font()
        f.setPointSize(22); f.setBold(True)
        self.lbl_total.setFont(f)

        self.btn_finalize = QtWidgets.QPushButton("Finalizează (F12)")
        self.btn_cancel = QtWidgets.QPushButton("Anulează (Esc)")
        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.lbl_total)
        btns.addStretch()
        btns.addWidget(self.btn_finalize)
        btns.addWidget(self.btn_cancel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.table)
        layout.addLayout(btns)

        # ---- events ----
        self.btn_add.clicked.connect(self.add_line)
        self.btn_finalize.clicked.connect(self.finalize)
        self.btn_cancel.clicked.connect(self.reject)
        QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self.add_line)
        QtGui.QShortcut(QtGui.QKeySequence("Enter"),  self, activated=self.add_line)
        QtGui.QShortcut(QtGui.QKeySequence("F12"),    self, activated=self.finalize)
        QtGui.QShortcut(QtGui.QKeySequence("Esc"),    self, activated=self.reject)

        self.in_barcode.setFocus()
        self.refresh()

    # ---------------- actions ----------------
    def add_line(self):
        raw = self.in_barcode.text().strip()
        if not raw:
            return

        # validare/normalizare EAN/UPC
        try:
            code = normalize_barcode(raw)
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Cod invalid", str(e))
            self.in_barcode.setFocus(); self.in_barcode.selectAll()
            return

        qty = float(self.in_qty.value())
        if qty <= 0:
            QtWidgets.QMessageBox.warning(self, "Eroare", "Cantitatea trebuie > 0.")
            return

        # dacă produsul e 'buc', nu permitem zecimale
        p = self.svc.find_product_by_barcode(code)
        if not p:
            QtWidgets.QMessageBox.warning(self, "Eroare", "Produs inexistent. Adaugă-l întâi la Intrare.")
            return
        if p["unit"] == "buc" and abs(qty - round(qty)) > 1e-9:
            QtWidgets.QMessageBox.warning(self, "Eroare", "Cantitatea pentru 'buc' trebuie să fie întreagă.")
            return

        try:
            self.svc.add_line_to_receipt(self.receipt_id, code, qty)
            # reset
            self.in_barcode.clear()
            self.in_qty.setValue(1.000)
            self.in_barcode.setFocus()
            self.refresh()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Eroare", str(e))

    def refresh(self):
        data = self.svc.get_receipt(self.receipt_id)
        items = data["items"]

        self.table.setRowCount(0)
        for idx, it in enumerate(items, start=1):
            r = self.table.rowCount()
            self.table.insertRow(r)

            qty_base = int(it["qty_base"])
            unit = it["unit"]
            qty_text = str(qty_base) if unit == "buc" else f"{qty_base/1000:.3f}"
            subtotal_lei = it["line_total_cents"] / 100.0

            it0 = QtWidgets.QTableWidgetItem(str(idx))
            it0.setData(QtCore.Qt.UserRole, it["id"])  # păstrăm id linie pentru ștergere
            self.table.setItem(r, 0, it0)
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(it["name"]))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(it["barcode"] or ""))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(qty_text))
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(f"{subtotal_lei:.2f} lei"))

        total_lei = data["total_cents"] / 100.0
        self.lbl_total.setText(f"Total: {total_lei:.2f} lei")
        self.btn_finalize.setEnabled(len(items) > 0)

    def finalize(self):
        try:
            self.svc.finalize_receipt(self.receipt_id)
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Eroare la finalizare", str(e))

    # ---------------- utilities ----------------
    def _selected_line_id(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        item0 = self.table.item(r, 0)
        return item0.data(QtCore.Qt.UserRole) if item0 else None

    def remove_selected_line(self):
        line_id = self._selected_line_id()
        if not line_id:
            return
        self.svc.remove_line(int(line_id))
        self.refresh()

    def _table_menu(self, pos):
        line_id = self._selected_line_id()
        if not line_id:
            return
        menu = QtWidgets.QMenu(self)
        act = menu.addAction("Șterge linia")
        # PySide6: exec(), nu exec_()
        if menu.exec(self.table.viewport().mapToGlobal(pos)) == act:
            self.svc.remove_line(int(line_id))
            self.refresh()

    # Anulează bonul deschis dacă se iese cu Esc / butonul Anulează
    def reject(self):
        try:
            self.svc.void_receipt(self.receipt_id)
        except Exception:
            pass
        super().reject()
