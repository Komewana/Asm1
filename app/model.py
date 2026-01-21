import traceback
from typing import Tuple, Any
import cv2

from .config import MODEL_PATH

_yolo = None
_yolo_names = None
_yolo_err = None


def load_model():
    global _yolo, _yolo_names, _yolo_err
    try:
        from ultralytics import YOLO
        _yolo = YOLO(MODEL_PATH)
        _yolo_names = _yolo.names
        _yolo_err = None
        print("[YOLO] Loaded:", MODEL_PATH)
    except Exception as e:
        _yolo = None
        _yolo_names = None
        _yolo_err = str(e)
        print("[YOLO] Load failed:", e)
        print(traceback.format_exc())


def safe_imread(path: str):
    img = cv2.imread(path)
    if img is None:
        try:
            import numpy as np
            with open(path, 'rb') as f:
                img_array = np.asarray(bytearray(f.read()), dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception:
            pass
    if img is None:
        raise RuntimeError(f"cv2.imread failed: {path}")
    return img


def infer_and_annotate(image_path: str) -> Tuple[str, float, Any]:
    if _yolo is None:
        raise RuntimeError(f"YOLO not loaded: {_yolo_err}")

    _ = safe_imread(image_path)
    results = _yolo(image_path, verbose=False)
    if not results:
        return "Unknown", 0.0, None

    r = results[0]
    labels = []

    # OBB
    if hasattr(r, "obb") and r.obb is not None:
        cls = getattr(r.obb, "cls", None)
        conf = getattr(r.obb, "conf", None)
        if cls is not None and conf is not None:
            cls_list = cls.detach().cpu().tolist()
            conf_list = conf.detach().cpu().tolist()
            for c, cf in zip(cls_list, conf_list):
                idx = int(c)
                name = _yolo_names.get(idx, str(idx)) if isinstance(_yolo_names, dict) else str(idx)
                labels.append({"name": name, "conf": float(cf)})

    # Boxes
    if not labels and hasattr(r, "boxes") and r.boxes is not None:
        cls = getattr(r.boxes, "cls", None)
        conf = getattr(r.boxes, "conf", None)
        if cls is not None and conf is not None:
            cls_list = cls.detach().cpu().tolist()
            conf_list = conf.detach().cpu().tolist()
            for c, cf in zip(cls_list, conf_list):
                idx = int(c)
                name = _yolo_names.get(idx, str(idx)) if isinstance(_yolo_names, dict) else str(idx)
                labels.append({"name": name, "conf": float(cf)})

    labels.sort(key=lambda x: x["conf"], reverse=True)
    if labels:
        top1_name = labels[0]["name"]
        top1_conf = labels[0]["conf"]
    else:
        top1_name, top1_conf = "Unknown", 0.0

    ann = None
    try:
        ann = r.plot()
    except Exception:
        ann = None

    return top1_name, float(top1_conf), ann
