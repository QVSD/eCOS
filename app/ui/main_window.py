from PySide6 import QtWidgets, QtCore, QtGui
from ..util.config import load_config
from ..infra.db_init import init_db
from ..services.use_cases import InventoryService
from .intrare_dialog import IntrareDialog
from .vanzare_dialog import VanzareDialog
from .stoc_window import StocWindow
from .expirare_window import ExpirareWindow


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Inventar Magazin - MVP (Faza 0)")
        self.resize(900, 600)

        self.cfg = load_config()
        self.conn = init_db(self.cfg["db_path"])
        self.svc = InventoryService(self.cfg["db_path"])

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # Butoane mari
        self.btn_intrare = QtWidgets.QPushButton("Intrare în stoc (F1)")
        self.btn_vanzare = QtWidgets.QPushButton("Vânzare / Ieșire (F2)")
        self.btn_stoc = QtWidgets.QPushButton("Stoc curent (F3)")
        self.btn_expirare = QtWidgets.QPushButton("Alerte expirare (F4)")

        self.btn_setari = QtWidgets.QPushButton("Setări & Backup (F10)")
        for b in (self.btn_intrare, self.btn_vanzare, self.btn_stoc, self.btn_setari):
            b.setMinimumHeight(64)
            b.setStyleSheet("font-size: 22px;")

        layout.addWidget(self.btn_intrare)
        layout.addWidget(self.btn_vanzare)
        layout.addWidget(self.btn_stoc)
        layout.addStretch()
        layout.addWidget(self.btn_setari)
        layout.insertWidget(3, self.btn_expirare)

        self.statusBar().showMessage("Pregătit")

        # Conectări
        self.btn_intrare.clicked.connect(self.open_intrare)
        self.btn_vanzare.clicked.connect(self.open_vanzare)
        self.btn_stoc.clicked.connect(self.open_stoc)
        self.btn_setari.clicked.connect(self.open_setari)
        self.btn_expirare.clicked.connect(self.open_expirare)


        # Scurtături (pastram referințe ca să nu fie colectate)
        self.sc_f1  = QtGui.QShortcut(QtGui.QKeySequence("F1"),  self)
        self.sc_f2  = QtGui.QShortcut(QtGui.QKeySequence("F2"),  self)
        self.sc_f3  = QtGui.QShortcut(QtGui.QKeySequence("F3"),  self)
        self.sc_f4  = QtGui.QShortcut(QtGui.QKeySequence("F4"),  self)
        self.sc_f10 = QtGui.QShortcut(QtGui.QKeySequence("F10"), self)

        self.sc_f1.activated.connect(self.open_intrare)
        self.sc_f2.activated.connect(self.open_vanzare)
        self.sc_f3.activated.connect(self.open_stoc)
        self.sc_f4.activated.connect(self.open_expirare)
        self.sc_f10.activated.connect(self.open_setari)


    def open_intrare(self):
        dlg = IntrareDialog(self.svc, self)
        dlg.exec()

    def open_vanzare(self):
        dlg = VanzareDialog(self.svc, self)
        dlg.exec()

    def open_stoc(self):
        dlg = StocWindow(self.svc, self)
        dlg.exec()

    def open_setari(self):
        QtWidgets.QMessageBox.information(self, "Setări & Backup", "Aici vei seta backup zilnic, praguri alerte etc.")

    def open_expirare(self):
        dlg = ExpirareWindow(self.svc, self)
        dlg.exec()

