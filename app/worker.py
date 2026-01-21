import os
import time
import shutil
import threading
import re
from datetime import datetime
from typing import List, Optional

from .config import INPUT_DIR, OUTPUT_DIR, EXTS, POLL_SECONDS, STABLE_SECONDS, LAST_RAW
from .model import infer_and_annotate
from .db import db_insert

stop_flag = False

# Hỗ trợ: img_YYYYMMDD_HHMMSS.jpg | cam_YYYYMMDD_HHMMSS.jpg | YYYYMMDD_HHMMSS.jpg
_TS_RE = re.compile(r"(?:img_|cam_)?(\d{8})_(\d{6})", re.IGNORECASE)


def timestamp_from_filename(path: str) -> Optional[str]:
    name = os.path.basename(path)
    m = _TS_RE.search(name)
    if not m:
        return None
    ymd = m.group(1)
    hms = m.group(2)
    try:
        dt = datetime.strptime(ymd + hms, "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def list_images_sorted(folder: str) -> List[str]:
    files = []
    if not os.path.exists(folder):
        return []
    for n in os.listdir(folder):
        p = os.path.join(folder, n)
        if not os.path.isfile(p):
            continue
        if os.path.splitext(n)[1].lower() in EXTS:
            files.append(p)
    files.sort(key=lambda p: os.path.getmtime(p))
    return files


def file_stable(path: str, stable_seconds: float) -> bool:
    try:
        s1 = os.path.getsize(path)
        time.sleep(stable_seconds)
        s2 = os.path.getsize(path)
        return s1 == s2 and s2 > 0
    except Exception:
        return False


def make_output_name(src_path: str, product_name: str) -> str:
    base = os.path.basename(src_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pn = (product_name or "Unknown").strip().replace(" ", "_")
    pn = "".join(ch for ch in pn if ch.isalnum() or ch in ("_", "-", "."))
    name, ext = os.path.splitext(base)
    ext = ext if ext.lower() in EXTS else ".jpg"
    return f"{ts}_{pn}_{name}{ext}"


def worker_loop():
    global stop_flag
    print(f"[WORKER] Watching: {INPUT_DIR}")
    print(f"[WORKER] Output (RAW IMAGES): {OUTPUT_DIR}")

    while not stop_flag:
        try:
            items = list_images_sorted(INPUT_DIR)
            if not items:
                time.sleep(POLL_SECONDS)
                continue

            src = items[0]
            if not file_stable(src, STABLE_SECONDS):
                time.sleep(POLL_SECONDS)
                continue

            # copy last raw
            try:
                shutil.copyfile(src, LAST_RAW)
            except Exception:
                pass

            # infer
            try:
                product_name, conf, _ann_img = infer_and_annotate(src)
            except Exception as e:
                print(f"[WORKER] Infer error: {e}")
                try:
                    os.remove(src)
                except Exception:
                    pass
                time.sleep(POLL_SECONDS)
                continue

            # save output raw
            out_name = make_output_name(src, product_name)
            out_path = os.path.join(OUTPUT_DIR, out_name)
            try:
                shutil.copyfile(src, out_path)
            except Exception as e:
                print(f"[WORKER] Save error: {e}")
                try:
                    os.remove(src)
                except Exception:
                    pass
                time.sleep(POLL_SECONDS)
                continue

            # remove input
            try:
                os.remove(src)
            except Exception as e:
                print(f"[WORKER] Delete src failed: {e}")

            # ✅ timestamp = từ filename ESP32
            ts_from_name = timestamp_from_filename(src)
            if ts_from_name is None:
                ts_from_name = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            brand = product_name if product_name else "Unknown"
            db_insert(ts_from_name, brand, product_name, conf, out_name)

            print(f"[AI] {product_name} ({conf:.2f}) -> Saved. ts={ts_from_name}")
            time.sleep(0.05)

        except Exception as e:
            print(f"[WORKER] Loop Error: {e}")
            time.sleep(1.0)


def start_worker_thread():
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    return t
