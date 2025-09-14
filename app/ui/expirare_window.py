from PySide6 import QtWidgets, QtCore
from ..services.use_cases import InventoryService

class ExpirareWindow(QtWidgets.QDialog):
    def __init__(self, svc: InventoryService, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.setWindowTitle("Alerte expirare")
        self.resize(720, 520)

        top = QtWidgets.QHBoxLayout()
        self.spin_days = QtWidgets.QSpinBox(); self.spin_days.setRange(1, 365); self.spin_days.setValue(7)
        self.btn_refresh = QtWidgets.QPushButton("Actualizează")
        top.addWidget(QtWidgets.QLabel("Zile până la expirare ≤"))
        top.addWidget(self.spin_days)
        top.addStretch()
        top.addWidget(self.btn_refresh)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Produs","Cod","Expiră la","În stoc","Zile"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)

        self.btn_refresh.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self):
        days = int(self.spin_days.value())
        items = self.svc.get_expiring_batches(days)
        self.table.setRowCount(0)
        for it in items:
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r,0, QtWidgets.QTableWidgetItem(it["product_name"] or ""))
            self.table.setItem(r,1, QtWidgets.QTableWidgetItem(it["barcode"] or ""))
            self.table.setItem(r,2, QtWidgets.QTableWidgetItem(it["expiry_date"]))
            st_text = f"{int(it['stock_human'])}" if float(it["stock_human"]).is_integer() else f"{it['stock_human']:.3f}"
            self.table.setItem(r,3, QtWidgets.QTableWidgetItem(st_text))
            self.table.setItem(r,4, QtWidgets.QTableWidgetItem(str(it["days_left"])))

            # mic highlight pt <=3 zile
            if it["days_left"] <= 3:
                for c in range(5):
                    cell = self.table.item(r, c)
                    if cell: cell.setBackground(QtCore.Qt.GlobalColor.yellow)
