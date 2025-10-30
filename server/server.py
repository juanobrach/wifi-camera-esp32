import os
import sys
import time
import io
import requests
from typing import Iterator, Optional

# Google Cloud Vision
from google.cloud import vision


def mjpeg_frames(url: str, timeout: int = 10) -> Iterator[bytes]:
    """Yield individual JPEG frames from an MJPEG HTTP stream."""
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        boundary = None
        ctype = resp.headers.get("Content-Type", "")
        # Example: multipart/x-mixed-replace; boundary=123456789000000000000987654321
        if "boundary=" in ctype:
            boundary = ctype.split("boundary=")[-1]
            if boundary.startswith("\"") and boundary.endswith("\""):
                boundary = boundary[1:-1]
        if not boundary:
            # Fallback common boundary used by ESP32-CAM
            boundary = "--123456789000000000000987654321"

        boundary_bytes = boundary.encode()
        buf = b""
        for chunk in resp.iter_content(chunk_size=4096):
            if not chunk:
                continue
            buf += chunk
            # Split on boundary
            while True:
                idx = buf.find(boundary_bytes)
                if idx < 0:
                    break
                part = buf[:idx]
                buf = buf[idx + len(boundary_bytes):]
                # Extract JPEG bytes inside the part
                # Look for JPEG start/end
                start = part.find(b"\xff\xd8")
                end = part.find(b"\xff\xd9")
                if start >= 0 and end > start:
                    yield part[start:end + 2]


def annotate_labels(client: vision.ImageAnnotatorClient, image_bytes: bytes):
    image = vision.Image(content=image_bytes)
    response = client.label_detection(image=image, max_results=10)
    if response.error.message:
        raise RuntimeError(response.error.message)
    return response.label_annotations


def main():
    esp_url = os.environ.get("ESP_STREAM_URL", "http://127.0.0.1:81/stream")
    sample_every_s = float(os.environ.get("SAMPLE_EVERY_SECONDS", "2.0"))

    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds or not os.path.exists(creds):
        print("ERROR: GOOGLE_APPLICATION_CREDENTIALS not set or file not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to MJPEG: {esp_url}")
    client = vision.ImageAnnotatorClient()

    last_time: float = 0.0
    for frame in mjpeg_frames(esp_url):
        now = time.time()
        if now - last_time < sample_every_s:
            continue
        last_time = now
        try:
            labels = annotate_labels(client, frame)
            top = ", ".join(
                f"{l.description} ({l.score:.2f})" for l in labels[:5])
            print(f"[{time.strftime('%H:%M:%S')}] Labels: {top}")
        except Exception as e:
            print(f"Annotate error: {e}")


if __name__ == "__main__":
    main()
