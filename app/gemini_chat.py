from typing import Any, Dict
import traceback
import json
from datetime import datetime

from .config import GEMINI_API_KEY, GEMINI_MODEL, USE_GEMINI
from .db import db_stats, db_count_filtered, db_stats_by_day, db_compare_products, db_get_csv_data

# --- CẤU HÌNH NHÂN CÁCH AI THÔNG MINH ---
SYSTEM_PROMPT = """
VAI TRÒ:
Bạn là Trợ lý Phân tích Dữ liệu kiêm Thư ký Kho hàng.

CHẾ ĐỘ XỬ LÝ YÊU CẦU:

1. **CHẾ ĐỘ XUẤT FILE (Ưu tiên cao nhất):**
   - Khi người dùng yêu cầu: "Xuất excel", "Tải file", "Gửi báo cáo", "Lấy file ngày hôm nay", "Cho file"...
   - **Hành động:** Bạn KHÔNG ĐƯỢC từ chối. Bạn hãy tạo một đường link tải file Excel.
   - **Cú pháp bắt buộc để tạo nút tải:** `[👉 Bấm vào đây để tải Excel Báo Cáo](/export_excel?start_date={START}&end_date={END}&product={PRODUCT})`
   
   - **Cách xác định ngày:** - "Hôm nay" = Ngày hiện tại (xem ở phần THỜI GIAN HIỆN TẠI bên dưới).
     - "Tháng này" = Từ ngày 1 đến hiện tại.
     - "Tất cả" = Để trống start_date và end_date.
   
   - **Ví dụ mẫu:**
     - Khách: "Cho tôi file excel hôm nay" (Hôm nay là 2026-01-17)
     - Bạn: "Dạ, báo cáo ngày 17/01 của bạn đây ạ: [👉 Bấm vào đây để tải Excel](/export_excel?start_date=2026-01-17&end_date=2026-01-17&product=)"

2. **CHẾ ĐỘ PHÂN TÍCH & TRA CỨU:**
   - Khi hỏi về số liệu ("Bao nhiêu", "Xu hướng", "Tại sao"):
   - Dựa vào CSV và JSON summary để trả lời ngắn gọn, chuyên nghiệp.

LƯU Ý: 
- Hệ thống chỉ hỗ trợ xuất file Excel (.xlsx). Nếu khách hỏi Word/PDF/Chart, hãy đưa link Excel và nói "Hiện hệ thống chỉ hỗ trợ xuất Excel, bạn tải về dùng tạm nhé".
"""

def build_summary(start: str, end: str, product: str) -> Dict[str, Any]:
    return {
        "filters": {"start_date": start, "end_date": end, "product": product},
        "total_records": db_count_filtered(start, end, product),
        "top_trending": db_stats(start, end, product, topk=5),
    }

def _fallback_rule_answer(question: str, start: str, end: str, product: str) -> str:
    # Luật cứng khi mất kết nối AI
    q = (question or "").strip().lower()
    
    # Nếu hỏi xuất file, tạo link luôn
    if any(x in q for x in ["excel", "xuất", "tải", "file", "báo cáo"]):
        return f"Bạn có thể tải dữ liệu tại đây: [👉 Tải Excel Ngay](/export_excel?start_date={start}&end_date={end}&product={product})"
    
    if not q: return "Mời nhập câu hỏi."
    stats = db_stats(start, end, product, topk=5)
    if not stats: return "Chưa có dữ liệu."
    lines = [f"{it['label']}: {it['count']}" for it in stats]
    return "Thống kê sơ bộ: " + ", ".join(lines)

def ask_gemini(question: str, start: str, end: str, product: str) -> str:
    if not USE_GEMINI or not GEMINI_API_KEY:
        return _fallback_rule_answer(question, start, end, product)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "Lỗi Server: Chưa cài thư viện google-genai."

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # 1. Chuẩn bị dữ liệu
        summary = build_summary(start, end, product)
        # Lấy 150 dòng để AI có cái nhìn tổng quan
        csv_data = db_get_csv_data(start, end, product, limit=150)
        
        if not csv_data.strip():
            csv_data = "(Chưa có dữ liệu)"

        # 2. Tools (Dùng cho câu hỏi phân tích)
        def run_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
            print(f"--- [AI Tool] {name} {args}")
            s = args.get("start_date") or start
            e = args.get("end_date") or end
            p = args.get("product") or product
            
            if name == "analyze_trend": 
                return {"data": db_stats_by_day(s, e, p)}
            if name == "compare_products": 
                return {"data": db_compare_products(s, e, args.get("product_a"), args.get("product_b"))}
            return {"error": "Unknown tool"}

        tools = [
            types.Tool(function_declarations=[
                types.FunctionDeclaration(name="analyze_trend", description="Xem xu hướng", parameters={"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}, "product": {"type": "string"}}}),
                types.FunctionDeclaration(name="compare_products", description="So sánh", parameters={"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}, "product_a": {"type": "string"}, "product_b": {"type": "string"}}, "required": ["product_a", "product_b"]}),
            ])
        ]

        # 3. Prompt Engineering
        # Cung cấp thời gian thực để AI tính ngày "Hôm nay" chính xác
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        full_prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"THỜI GIAN HIỆN TẠI: {current_time_str}\n"
            f"--- CSV SNIPPET ---\n{csv_data}\n"
            f"--- JSON SUMMARY ---\n{json.dumps(summary, ensure_ascii=False)}\n\n"
            f"USER: \"{question}\"\n"
            f"AI:"
        )

        contents = [types.Content(role="user", parts=[types.Part(text=full_prompt)])]

        # 4. Gọi Model
        # Temperature 0.3: Đủ thấp để tạo link chính xác, đủ cao để phân tích mượt mà
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(tools=tools, temperature=0.3)
        )

        if not resp.candidates: return "Hệ thống bận."
        cand = resp.candidates[0]
        
        # Xử lý Tool Call (nếu có)
        tool_calls = [p.function_call for p in cand.content.parts if p.function_call] if cand.content.parts else []

        if not tool_calls:
            return (cand.content.parts[0].text if cand.content.parts else "...")

        tool_parts = []
        for call in tool_calls:
            res = run_tool(call.name, dict(call.args or {}))
            tool_parts.append(types.Part(function_response=types.FunctionResponse(name=call.name, response=res)))
        
        contents.append(cand.content)
        contents.append(types.Content(role="tool", parts=tool_parts))
        
        # Gọi lại lần 2 sau khi có kết quả tool
        resp2 = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.3)
        )
        
        if resp2.candidates and resp2.candidates[0].content.parts:
            return resp2.candidates[0].content.parts[0].text
            
        return "Đang xử lý..."

    except Exception as e:
        traceback.print_exc()
        return f"Lỗi AI: {str(e)}"