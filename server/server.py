import os
import sys
import time
import io
import json
import requests
from typing import Iterator, Optional, List, Tuple
from PIL import Image
import numpy as np
import cv2


def log(msg: str) -> None:
    """Lightweight logger with time prefix."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def mjpeg_frames(url: str, timeout: int = 10) -> Iterator[bytes]:
    """Yield individual JPEG frames from an MJPEG HTTP stream."""
    log(f"Connecting to stream: {url}")
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        log(f"HTTP {resp.status_code}; Content-Type: {resp.headers.get('Content-Type', '')}")
        boundary = None
        ctype = resp.headers.get("Content-Type", "")
        if "boundary=" in ctype:
            boundary = ctype.split("boundary=")[-1]
            if boundary.startswith("\"") and boundary.endswith("\""):
                boundary = boundary[1:-1]
        if not boundary:
            boundary = "--123456789000000000000987654321"
        # Normalize: body uses lines that start with `--<boundary>`; ensure prefix exists
        if not boundary.startswith("--"):
            boundary = "--" + boundary

        boundary_bytes = boundary.encode()
        buf = b""
        got_any = False
        last_wait_log = time.time()
        for chunk in resp.iter_content(chunk_size=4096):
            if not chunk:
                continue
            buf += chunk
            if not got_any and (time.time() - last_wait_log) > 5:
                log("Connected, waiting for first frame...")
                last_wait_log = time.time()
            while True:
                idx = buf.find(boundary_bytes)
                if idx < 0:
                    break
                part = buf[:idx]
                buf = buf[idx + len(boundary_bytes):]
                start = part.find(b"\xff\xd8")
                end = part.find(b"\xff\xd9")
                if start >= 0 and end > start:
                    if not got_any:
                        log("First frame received")
                        got_any = True
                    yield part[start:end + 2]


def load_config() -> dict:
    """
    Load configuration from JSON with environment variable overrides.
    CONFIG_PATH can point to a different JSON file.
    """
    defaults = {
        "ESP_STREAM_URL": "http://192.168.1.87:81/stream",
        "SAMPLE_EVERY_SECONDS": 1.5,
        "HF_MODEL": "google/vit-base-patch16-224",
        "TOP_K": 5,
        "HF_DEVICE": None  # "cpu", "mps", or cuda index string like "0"
    }
    cfg_path = os.environ.get(
        "CONFIG_PATH",
        os.path.join(os.path.dirname(__file__), "config.json")
    )
    cfg = dict(defaults)
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
            if isinstance(file_cfg, dict):
                cfg.update(
                    {k: v for k, v in file_cfg.items() if v is not None})
        except Exception as e:
            print(
                f"Warning: failed to load config file '{cfg_path}': {e}", file=sys.stderr)

    # Environment overrides (strings); coerce known types
    if "ESP_STREAM_URL" in os.environ:
        cfg["ESP_STREAM_URL"] = os.environ["ESP_STREAM_URL"]
    if "SAMPLE_EVERY_SECONDS" in os.environ:
        try:
            cfg["SAMPLE_EVERY_SECONDS"] = float(
                os.environ["SAMPLE_EVERY_SECONDS"])
        except ValueError:
            pass
    if "HF_MODEL" in os.environ:
        cfg["HF_MODEL"] = os.environ["HF_MODEL"]
    if "TOP_K" in os.environ:
        try:
            cfg["TOP_K"] = int(os.environ["TOP_K"])
        except ValueError:
            pass
    if "HF_DEVICE" in os.environ:
        v = os.environ["HF_DEVICE"].strip()
        cfg["HF_DEVICE"] = v if v else None

    log(
        "Config loaded: "
        f"url={cfg['ESP_STREAM_URL']} sample_every={cfg['SAMPLE_EVERY_SECONDS']}s "
        f"model={cfg['HF_MODEL']} top_k={cfg['TOP_K']} device={cfg['HF_DEVICE'] or 'auto'}"
    )
    return cfg


def build_classifier(model_name: Optional[str] = None, device: Optional[str] = None, top_k: int = 5):
    from transformers import pipeline
    model = model_name or "google/vit-base-patch16-224"
    pipe_kwargs = {"model": model, "top_k": top_k}
    if device:
        pipe_kwargs["device"] = device
    log(
        f"Initializing classifier: model={model} top_k={top_k} device={device or 'auto'}")
    clf = pipeline("image-classification", **pipe_kwargs)
    log("Classifier ready")
    return clf


def classify_bytes(clf, image_bytes: bytes, top_k: int = 5) -> List[Tuple[str, float]]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    preds = clf(img, top_k=top_k)
    if isinstance(preds, list) and preds and isinstance(preds[0], dict):
        items = preds
    elif isinstance(preds, dict):
        items = [preds]
    else:
        items = []
    return [(it.get("label", "?"), float(it.get("score", 0.0))) for it in items]


def decode_jpeg_to_bgr(frame_bytes: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(frame_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR
    return img


def draw_predictions_bgr(img: np.ndarray, preds: List[Tuple[str, float]]) -> np.ndarray:
    overlay = img.copy()
    x, y = 10, 22
    for i, (lbl, score) in enumerate(preds):
        text = f"{i+1}. {lbl} ({score:.2f})"
        cv2.putText(overlay, text, (x, y + i*22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
    return overlay


def main():
    cfg = load_config()
    esp_url = cfg["ESP_STREAM_URL"]
    sample_every_s = float(cfg["SAMPLE_EVERY_SECONDS"])
    model_name = cfg["HF_MODEL"]
    top_k = int(cfg["TOP_K"])
    device = cfg["HF_DEVICE"]

    log(
        f"Config file: {os.environ.get('CONFIG_PATH', os.path.join(os.path.dirname(__file__), 'config.json'))}"
    )

    try:
        clf = build_classifier(model_name=model_name,
                               device=device, top_k=top_k)
    except Exception as e:
        print(f"Failed to initialize classifier: {e}", file=sys.stderr)
        sys.exit(1)

    last_time: float = 0.0
    last_results: List[Tuple[str, float]] = []

    for frame in mjpeg_frames(esp_url):
        now = time.time()
        show_img = decode_jpeg_to_bgr(frame)
        if show_img is not None:
            # Dibuja lo último que tengas (para no bloquear la visualización)
            if last_results:
                show_img = draw_predictions_bgr(show_img, last_results)
            cv2.imshow("ESP32-CAM", show_img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        if now - last_time < sample_every_s:
            continue
        last_time = now

        try:
            results = classify_bytes(clf, frame, top_k=top_k)
            last_results = results  # guarda para overlay en frames siguientes
            top_line = ", ".join(
                f"{lbl} ({score:.2f})" for lbl, score in results[:top_k])
            print(f"[{time.strftime('%H:%M:%S')}] {top_line}")
        except Exception as e:
            print(f"Classify error: {e}", file=sys.stderr)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
