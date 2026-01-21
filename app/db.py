import sqlite3
from typing import List, Dict, Any, Optional
from .config import DB_PATH


def db_connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA temp_store=MEMORY;")
        con.execute("PRAGMA busy_timeout=3000;")
    except Exception:
        pass
    return con


def db_init():
    con = db_connect()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        brand TEXT,
        product_name TEXT,
        conf REAL,
        image_path TEXT
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_timestamp ON records(timestamp);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_records_product ON records(product_name);")
    con.commit()
    con.close()


def db_insert(timestamp: str, brand: str, product_name: str, conf: float, image_path: str) -> int:
    con = db_connect()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO records (timestamp, brand, product_name, conf, image_path)
        VALUES (?, ?, ?, ?, ?)
    """, (timestamp, brand, product_name, conf, image_path))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def _row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": r["id"],
        "timestamp": r["timestamp"],
        "brand": r["brand"] or "Unknown",
        "product_name": r["product_name"] or "Unknown",
        "conf": float(r["conf"] or 0.0),
        "image_path": r["image_path"] or ""
    }


def db_query_cursor(start_date: str, end_date: str, product: str, limit: int = 20, cursor_id: Optional[int] = None) -> List[Dict[str, Any]]:
    where = []
    params = []
    if start_date:
        where.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        where.append("timestamp <= ?")
        params.append(end_date)
    if product:
        where.append("product_name LIKE ?")
        params.append(f"%{product}%")
    if cursor_id is not None:
        where.append("id < ?")
        params.append(int(cursor_id))

    sql = "SELECT * FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))

    con = db_connect()
    cur = con.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()
    return [_row_to_dict(r) for r in rows]


def db_query_newer(start_date: str, end_date: str, product: str, last_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    where = ["id > ?"]
    params = [int(last_id)]
    if start_date:
        where.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        where.append("timestamp <= ?")
        params.append(end_date)
    if product:
        where.append("product_name LIKE ?")
        params.append(f"%{product}%")

    sql = "SELECT * FROM records WHERE " + " AND ".join(where)
    sql += " ORDER BY id ASC LIMIT ?"
    params.append(int(limit))

    con = db_connect()
    cur = con.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()
    return [_row_to_dict(r) for r in rows]


def db_stats(start_date: str, end_date: str, product: str, topk: int = 30) -> List[Dict[str, Any]]:
    where = []
    params = []
    if start_date:
        where.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        where.append("timestamp <= ?")
        params.append(end_date)
    if product:
        where.append("product_name LIKE ?")
        params.append(f"%{product}%")

    sql = "SELECT product_name AS label, COUNT(*) AS count FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY product_name ORDER BY count DESC LIMIT ?"
    params.append(int(topk))

    con = db_connect()
    cur = con.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()

    return [{"label": (r["label"] or "Unknown"), "count": int(r["count"])} for r in rows]


def db_count_all() -> int:
    con = db_connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM records")
    total = cur.fetchone()[0]
    con.close()
    return int(total)


def db_count_filtered(start_date: str, end_date: str, product: str) -> int:
    where = []
    params = []
    if start_date:
        where.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        where.append("timestamp <= ?")
        params.append(end_date)
    if product:
        where.append("product_name LIKE ?")
        params.append(f"%{product}%")
    
    sql = "SELECT COUNT(*) FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
        
    con = db_connect()
    cur = con.cursor()
    cur.execute(sql, params)
    total = cur.fetchone()[0]
    con.close()
    return int(total)


def db_stats_by_day(start_date: str, end_date: str, product: str) -> List[Dict[str, Any]]:
    where = []
    params = []
    if start_date:
        where.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        where.append("timestamp <= ?")
        params.append(end_date)
    if product:
        where.append("product_name LIKE ?")
        params.append(f"%{product}%")

    sql = "SELECT substr(timestamp, 1, 10) as day, COUNT(*) as count FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY day ORDER BY day ASC"

    con = db_connect()
    cur = con.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()
    return [{"day": r["day"], "count": r["count"]} for r in rows]


def db_compare_products(start_date: str, end_date: str, prod_a: str, prod_b: str) -> Dict[str, int]:
    count_a = db_count_filtered(start_date, end_date, prod_a)
    count_b = db_count_filtered(start_date, end_date, prod_b)
    return {prod_a: count_a, prod_b: count_b}


# === HÀM QUAN TRỌNG ĐỂ AI ĐỌC DỮ LIỆU ===
def db_get_csv_data(start_date: str, end_date: str, product: str, limit: int = 200) -> str:
    where = []
    params = []
    if start_date:
        where.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        where.append("timestamp <= ?")
        params.append(end_date)
    if product:
        where.append("product_name LIKE ?")
        params.append(f"%{product}%")
    
    sql = "SELECT id, timestamp, product_name FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    
    con = db_connect()
    cur = con.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    con.close()

    csv_lines = ["ID, Timestamp, Product"]
    for r in rows:
        name = (r["product_name"] or "Unknown").replace(",", " ")
        csv_lines.append(f"{r['id']}, {r['timestamp']}, {name}")
    
    return "\n".join(csv_lines)