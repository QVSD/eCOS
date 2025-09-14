from PySide6 import QtWidgets, QtCore, QtGui
from ..services.use_cases import InventoryService

#TO DO, caseta lot are elemente editabile

class LoturiDialog(QtWidgets.QDialog):
    def __init__(self, svc: InventoryService, product_id: int, product_name: str, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.product_id = product_id
        self.setWindowTitle(f"Loturi – {product_name}")
        self.resize(560, 420)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Lot", "Expirare", "Stoc", "Observație"])
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        def _datestr(v):
            if not v:
                return ""
            # suportă TEXT, datetime.date/datetime
            return getattr(v, "isoformat", lambda: str(v))()

        items = self.svc.get_product_batches(self.product_id)
        self.table.setRowCount(0)
        for it in items:
            r = self.table.rowCount()
            self.table.insertRow(r)

            # LOT
            lot_text = it.get("lot_code") or "(fără lot)"
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(lot_text))

            # Expirare (mereu string)
            exp_text = _datestr(it.get("expiry_date"))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(exp_text))

            # Stoc
            st = it["stock_human"]
            st_text = f"{int(st)}" if float(st).is_integer() else f"{st:.3f}"
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(st_text))

            # Observație (expirare apropiată)
            obs = ""
            if exp_text:
                qd = QtCore.QDate.fromString(exp_text, "yyyy-MM-dd")
                if qd.isValid():
                    days = QtCore.QDate.currentDate().daysTo(qd)
                    if days <= 7:
                        obs = f"⚠ în {days} zile" if days >= 0 else f"expirat acum {-days} zile"
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(obs))

        self.table.resizeColumnsToContents()



class StocWindow(QtWidgets.QDialog):
    def __init__(self, svc: InventoryService, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.setWindowTitle("Stoc curent")
        self.resize(900, 600)

        # --- filtre ---
        filt = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit(); self.search.setPlaceholderText("Caută nume sau cod...")
        self.low_only = QtWidgets.QCheckBox("Doar stoc scăzut")
        self.low_threshold = QtWidgets.QDoubleSpinBox()
        self.low_threshold.setDecimals(3); self.low_threshold.setMaximum(1e9); self.low_threshold.setValue(5.0)
        self.btn_refresh = QtWidgets.QPushButton("Actualizează")

        filt.addWidget(self.search, 2)
        filt.addWidget(self.low_only)
        filt.addWidget(QtWidgets.QLabel("Prag (în unitatea produsului):"))
        filt.addWidget(self.low_threshold)
        filt.addStretch()
        filt.addWidget(self.btn_refresh)

        # --- tabel produse ---
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Denumire", "Cod", "Unit.", "Stoc"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        # --- butoane ---
        self.btn_loturi = QtWidgets.QPushButton("Detalii loturi")
        self.btn_export = QtWidgets.QPushButton("Export CSV")
        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.btn_loturi); btns.addStretch(); btns.addWidget(self.btn_export)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(filt)
        layout.addWidget(self.table)
        layout.addLayout(btns)

        # --- events ---
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_loturi.clicked.connect(self.open_loturi)
        self.table.doubleClicked.connect(self.open_loturi)
        self.search.returnPressed.connect(self.refresh)
        self.btn_export.clicked.connect(self.export_csv)

        self.refresh()

    def refresh(self):
        threshold = float(self.low_threshold.value())
        items = self.svc.get_stock_products(
            search=self.search.text().strip(),
            low_only=self.low_only.isChecked(),
            low_threshold_human=threshold,           # prag în buc/kg/l, după unitatea produsului
        )

        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)          # nu lăsăm Qt să re-sorteze în timp ce populăm

        self.table.setRowCount(0)
        for idx, it in enumerate(items, start=1):
            r = self.table.rowCount(); self.table.insertRow(r)

            # # (1) cu product_id în UserRole
            cell0 = QtWidgets.QTableWidgetItem(str(idx))
            cell0.setData(QtCore.Qt.UserRole, it["product_id"])
            self.table.setItem(r, 0, cell0)

            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(it["name"] or ""))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(it["barcode"] or ""))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(it["unit"]))

            st = it["stock_human"]
            st_text = f"{int(st)}" if float(st).is_integer() else f"{st:.3f}"
            cell_st = QtWidgets.QTableWidgetItem(st_text)
            cell_st.setData(QtCore.Qt.EditRole, float(st))  # sortare numerică pe „Stoc”
            self.table.setItem(r, 4, cell_st)

            # highlight stoc scăzut (doar când nu e filtrul activ)
            if (not self.low_only.isChecked()) and (it["stock_human"] <= threshold):
                for c in range(5):
                    cell = self.table.item(r, c)
                    if cell:
                        cell.setBackground(QtGui.QColor(255, 245, 200))

        self.table.setSortingEnabled(was_sorting)
        if was_sorting:
            self.table.sortItems(1, QtCore.Qt.AscendingOrder)  # denumire
        self.table.resizeColumnsToContents()

    def open_loturi(self):
        row = self.table.currentRow()
        if row < 0: return
        cell_id = self.table.item(row, 0)
        cell_name = self.table.item(row, 1)
        product_id = cell_id.data(QtCore.Qt.UserRole) if cell_id else None
        product_name = cell_name.text() if cell_name else ""
        if not product_id: return
        dlg = LoturiDialog(self.svc, int(product_id), product_name, self)
        dlg.exec()

    def export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV", "stoc.csv", "CSV Files (*.csv)")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["#","Denumire","Cod","Unit.","Stoc"])
            # pentru export folosim exact lista din refresh
            threshold = float(self.low_threshold.value())
            items = self.svc.get_stock_products(
                search=self.search.text().strip(),
                low_only=self.low_only.isChecked(),
                low_threshold_human=threshold,
            )
            for idx, it in enumerate(items, start=1):
                st = it["stock_human"]
                st_val = int(st) if float(st).is_integer() else round(st, 3)
                w.writerow([idx, it["name"] or "", it["barcode"] or "", it["unit"], st_val])
        QtWidgets.QMessageBox.information(self, "Export", "Export efectuat.")
