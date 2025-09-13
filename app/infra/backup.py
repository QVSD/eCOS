import sqlite3
from pathlib import Path
from datetime import datetime

def make_backup(db_path: str, backup_dir: str):
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst_path = Path(backup_dir) / f"magazin_{stamp}.sqlite"
    with sqlite3.connect(db_path) as src, sqlite3.connect(dst_path) as dst:
        src.backup(dst)  # copie consistentă
    return str(dst_path)
