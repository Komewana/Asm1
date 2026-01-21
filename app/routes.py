import io
import os
import time
import json
import traceback
from datetime import datetime

from flask import Blueprint, request, jsonify, Response, send_from_directory, render_template, stream_with_context
from openpyxl import Workbook

from .config import STATIC_DIR, OUTPUT_DIR, INPUT_DIR
from .db import db_query_cursor, db_query_newer, db_stats, db_count_all
from .gemini_chat import ask_gemini

bp = Blueprint("routes", __name__)

_stats_cache = {"key": None, "ts": 0.0, "data": None}
STATS_CACHE_SECONDS = 2.0


@bp.get("/health")
def health():
    return jsonify({"ok": True})


@bp.get("/")
def home():
    return render_template("index.html")


@bp.get("/static/<path:filename>")
def static_files(filename: str):
    return send_from_directory(STATIC_DIR, filename)


@bp.get("/uploads/<path:filename>")
def uploads(filename: str):
    return send_from_directory(OUTPUT_DIR, filename)


@bp.get("/api/count_all")
def api_count_all():
    return jsonify({"total": db_count_all()})


@bp.get("/api/data")
def api_data():
    start = request.args.get("start_date", "")
    end = request.args.get("end_date", "")
    product = request.args.get("product", "")

    # --- SỬA LỖI HIỂN THỊ DỮ LIỆU KHI CHỌN NGÀY ---
    # Nếu chỉ truyền ngày (YYYY-MM-DD), tự động thêm giờ để bao trọn ngày
    if start and len(start) == 10: 
        start += " 00:00:00"
    if end and len(end) == 10:     
        end += " 23:59:59"
    # ----------------------------------------------

    try:
        limit = int(request.args.get("limit", "20"))
    except Exception:
        limit = 20
    limit = max(1, min(limit, 200))

    cursor_id = None
    cursor_raw = request.args.get("cursor_id", "")
    if cursor_raw.isdigit():
        cursor_id = int(cursor_raw)

    rows = db_query_cursor(start, end, product, limit=limit, cursor_id=cursor_id)
    return jsonify(rows)


@bp.get("/api/stats")
def api_stats():
    start = request.args.get("start_date", "")
    end = request.args.get("end_date", "")
    product = request.args.get("product", "")

    # Cũng áp dụng fix ngày cho stats
    if start and len(start) == 10: start += " 00:00:00"
    if end and len(end) == 10: end += " 23:59:59"

    key = f"{start}|{end}|{product}"
    now = time.time()

    if _stats_cache["key"] == key and (now - _stats_cache["ts"] <= STATS_CACHE_SECONDS):
        return jsonify(_stats_cache["data"])

    data = db_stats(start, end, product, topk=30)
    _stats_cache.update({"key": key, "ts": now, "data": data})
    return jsonify(data)


@bp.post("/api/chat")
def api_chat():
    try:
        data = request.json or {}
        question = data.get("question", "")
        
        start = data.get("start_date", "")
        end = data.get("end_date", "")
        product = data.get("product", "")

        # Fix ngày cho chat context luôn
        if start and len(start) == 10: start += " 00:00:00"
        if end and len(end) == 10: end += " 23:59:59"

        answer = ask_gemini(question, start, end, product)
        return jsonify({"answer": answer})
        
    except Exception as e:
        print("------- SERVER CHAT ERROR -------")
        traceback.print_exc()
        return jsonify({"answer": f"Lỗi hệ thống: {str(e)}"}), 200


@bp.get("/api/stream")
def api_stream():
    start = request.args.get("start_date", "")
    end = request.args.get("end_date", "")
    product = request.args.get("product", "")

    if start and len(start) == 10: start += " 00:00:00"
    if end and len(end) == 10: end += " 23:59:59"

    last_id_raw = request.args.get("last_id", "0")
    last_id = int(last_id_raw) if last_id_raw.isdigit() else 0

    @stream_with_context
    def gen():
        nonlocal last_id
        yield "retry: 1000\n\n"

        while True:
            try:
                rows = db_query_newer(start, end, product, last_id=last_id, limit=50)
                if rows:
                    for r in rows:
                        last_id = max(last_id, int(r["id"]))
                        payload = json.dumps(r, ensure_ascii=False)
                        yield f"event: new\n"
                        yield f"data: {payload}\n\n"
                else:
                    yield ": keep-alive\n\n"

                time.sleep(0.5)
            except GeneratorExit:
                break
            except Exception:
                yield ": error\n\n"
                time.sleep(1.0)

    return Response(gen(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no"
    })


# --- ĐÂY LÀ PHẦN SỬA QUAN TRỌNG NHẤT ---
@bp.get("/export_excel")
def export_excel():
    start = request.args.get("start_date", "")
    end = request.args.get("end_date", "")
    product = request.args.get("product", "")

    # ✅ FIX LỖI EXCEL TRỐNG: Tự động mở rộng thời gian
    # Nếu start/end chỉ là ngày (độ dài 10 ký tự: YYYY-MM-DD), ta thêm giờ vào
    if start and len(start) == 10:
        start += " 00:00:00"
    if end and len(end) == 10:
        end += " 23:59:59"  # Lấy đến hết giây cuối cùng của ngày

    rows = []
    cursor_id = None
    while True:
        # Gọi db_query_cursor với thời gian đã được fix
        batch = db_query_cursor(start, end, product, limit=500, cursor_id=cursor_id)
        if not batch:
            break
        rows.extend(batch)
        cursor_id = batch[-1]["id"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Vision Drink Survey"
    
    # Header
    ws.append(["ID", "Thời gian phát hiện", "Tên sản phẩm"])
    
    # Data
    for r in rows:
        ws.append([r["id"], r["timestamp"], r["product_name"]])

    # Auto-adjust column width (Tuỳ chọn làm đẹp)
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 15

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    fname = f"Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'}
    )


@bp.post("/api/upload_cam")
def upload_cam():
    f = request.files.get("file") or request.files.get("image")
    if not f:
        return jsonify({"ok": False, "error": "missing file"}), 400

    os.makedirs(INPUT_DIR, exist_ok=True)

    filename = (f.filename or "").strip()
    if not filename:
        filename = f"img_{int(time.time())}.jpg"

    safe = []
    for ch in filename:
        if ch.isalnum() or ch in ("_", "-", "."):
            safe.append(ch)
    filename = "".join(safe)

    if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
        filename += ".jpg"

    save_path = os.path.join(INPUT_DIR, filename)
    if os.path.exists(save_path):
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{int(time.time()*1000)}{ext}"
        save_path = os.path.join(INPUT_DIR, filename)

    f.save(save_path)
    return jsonify({"ok": True, "filename": filename})