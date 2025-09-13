# The central place where I am holding the application settings
# It doesnt influence the code that much but its important for the app behaviour
# Exactly as it is called, this file its a configuration file

from pathlib import Path
import json

# ------------------------------ DEFAULT CONFIGURATION PARAMETERS -----------------------------
# db_path = where is the Database going to be stored at (used by db.py, db_init.py, InventoryService, etc.)
# backup_dir = the implicit directory used for the backup to be saved at
# expiry_alert_days = warning for Product expir date
# low_stock_treshold = minimum treshold to be warned by the app that the store needs to be refilled
# locale = region code, used for number format, currency, calendaristic date, etc.
# TO DO  : db_mode and api_base_url to be updated

DEFAULT_CONFIG = {
    "db_path": "magazin.sqlite",
    "backup_dir": "backups",
    "expiry_alert_days": [7, 14, 30],
    "low_stock_threshold": 5,
    "locale": "ro_RO",
    "db_mode": "local",                      # pregătit pentru server
    "api_base_url": "http://localhost:8080"  # pentru viitor (mobil/API)
}

# ---------------------------     LOADING THE CONFIGURATION    ---------------------------------
# As, the first time when we are running the app on a new system, the config.json file doesnt exist
# The method checks if the file exists, if not it creates the file with default values, and if it
# does yes only reads it
def load_config(path: str = "config.json"):
    p = Path(path)
    if not p.exists():
        save_config(DEFAULT_CONFIG, path)
        return DEFAULT_CONFIG.copy() # return a copy so we are not altering the default configuration by mistake
    return json.loads(p.read_text(encoding="utf-8"))

def save_config(cfg: dict, path: str = "config.json"):
    Path(path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
