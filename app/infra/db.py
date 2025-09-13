import sqlite3
from pathlib import Path

# ---------------------------- DATABASE CONNECTION AND SETTINGS -----------------------------
# Creates the parent dir of DB file if missing
# Opens the sqslite3.connect connection with :
#   - detect_types = sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES → SQLite will try conversions of type (date/time).
#   - row_factory = sqlite3.Row → rows can be accesed as a dict (key = name col).

def connect(db_path: str):
    p = Path(db_path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)

    # To elaborate why I choose this expression;
    # Normally, when you do a sqlite3 querry, it is a tuple list : 
    
    # cur = conn.execute("SELECT id, name FROM products")
    # row = cur.fetchone()
    # print(row)  # (1, "Bananas")
    
    # So if we set it like we did here, then every row becomes an Row object that acts as a dictionary :
   
    # print(row["id"])    # 1
    # print(row["name"])  # Bananas

    conn.row_factory = sqlite3.Row

    # PRAGMA 
    # - it is a keyword specially used in SQLite (and exclusively on it), to set the internal options of the DB engine.
    # - there we are using three types of PRAGMAS :

    # Write-Ahead Logging : how journal holds the changes, and with this option it allows the reads to be performed while
    #                       you are writing  data
    conn.execute("PRAGMA journal_mode=WAL;")  

    # How often the SQLite synchronize the date with the disk (options: FULL, NORMAL, OFF)
    # NORMAL = more balanced, between safety of the data and speed. If we lost connection the risk of losing data its smaller
    conn.execute("PRAGMA synchronous=NORMAL;")

    # by default the constraints of type FOREIGN KEY are disabled.
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

# ---------------------------------- INTEGRITY CHECK -----------------------------------
# PRAGMA intergrity check returns a table with 1 column and 1 row (can be either 'ok' or 'error')
# fetchone takes only one row from the querry result
# e.g : fetchone () = ("ok",))
#       fetchone()[0] = ok

def integrity_check(conn):
    return conn.execute("PRAGMA integrity_check;").fetchone()[0]
