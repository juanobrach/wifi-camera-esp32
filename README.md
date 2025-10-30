# CameraWebServer (ESP32‑S CAM via Arduino UNO R3 bridge)

This project runs the ESP32 Camera Web Server example adapted for ESP32‑S‑CAM/ESP32‑CAM. It’s wired and flashed using an Arduino UNO R3 as a USB‑serial bridge.

<img width="1322" height="676" alt="camera_bb" src="https://github.com/user-attachments/assets/b6401121-c32a-445c-8968-904fd8cf28c1" />

## Hardware

- ESP32‑S‑CAM / ESP32‑CAM (OV2640), PSRAM module
- Arduino UNO R3 (as USB‑serial bridge)
- Stable 5V power (≥1A recommended)
- Short jumper wires, optional 470–1000 µF cap across 5V–GND at the camera board

## Board profile (Arduino IDE)

- Board: ESP32 Wrover Module
- Flash Mode: DIO
- Flash Frequency: 40 MHz
- PSRAM: Enabled
- Partition Scheme: Huge APP (3MB No OTA)
- Upload Speed: 115200 (use 57600 if unstable)
- Port: your `/dev/cu.usbmodem*` (macOS)

Tip: If you later switch to a pre‑defined camera board, you can also use “AI Thinker ESP32‑CAM” with the same Flash Mode/Frequency and PSRAM enabled.

## Wiring (UNO R3 as bridge)

- Hold UNO RESET to GND (kept held) so it acts as a dumb USB‑serial.
- Power: UNO 5V → ESP32 5V; UNO GND → ESP32 GND.
- Serial:
  - UNO TX (D1) → level‑shift → ESP32 U0R (GPIO3). Use divider: ~1 kΩ from TX to U0R, 2 kΩ from U0R to GND.
  - UNO RX (D0) ← ESP32 U0T (GPIO1) direct (3.3V is OK).
- Boot mode:
  - For flashing: IO0 → GND. Press ESP32 RST when “Connecting…” appears.
  - For normal run: remove IO0–GND, press RST.

## Project configuration

- Edit Wi‑Fi credentials in `CameraWebServer.ino`:
  - `const char *ssid = "..."`, `const char *password = "..."`
- Select the camera model in `board_config.h`. This repo is set to:
  - `#define CAMERA_MODEL_AI_THINKER`
- Pins are defined in `camera_pins.h` for the selected model.

## First run

1. Flash the sketch (see boot mode above).
2. Open Serial Monitor at 115200, wait for Wi‑Fi connect.
3. Copy the printed URL: `http://<device_ip>/` to view the stream.

## Make it faster (FPS)

- Lower resolution and increase JPEG compression:
  - In `setup()`, before init: `config.frame_size = FRAMESIZE_VGA` (or QVGA); `config.jpeg_quality = 20–25`; keep `config.fb_count = 2` when PSRAM is present.
- Keep `grab_mode = CAMERA_GRAB_LATEST`.
- Strong Wi‑Fi signal and stable 5V supply improve streaming.

## Troubleshooting

- Brownout resets: use a solid 5V (≥1A) to the 5V pin, short/thick wires, add a 470–1000 µF capacitor across 5V–GND.
- “Failed to connect / Invalid head of packet (0x65)”: check level shifting on UNO TX→ESP32 U0R, close Serial Monitor, try 57600 baud, press RST right when “Connecting…” appears.
- “Camera not supported (0x106)”: reseat the ribbon cable firmly; verify `CAMERA_MODEL_AI_THINKER` and correct pin map.

## Notes

- After flashing, you can disconnect RX/TX and leave only 5V/GND for standalone operation.
- If you switch to a dedicated USB‑UART (CP2102/CH340 at 3.3V), auto‑reset (DTR/RTS) can simplify uploads.

## Send the stream to a server

The camera serves MJPEG at `http://<device_ip>:81/stream`. You can forward (repackage/transcode) this on a server.

### Option A — Pull with FFmpeg (recommended)

- Re‑publish as RTMP (e.g., Nginx‑RTMP/YouTube/Twitch):

```bash
ffmpeg -f mjpeg -i http://<device_ip>:81/stream \
  -preset veryfast -tune zerolatency -vf scale=640:-1 -r 15 \
  -c:v libx264 -b:v 1500k -f flv rtmp://<rtmp_server>/live/stream
```

- Save segmented MP4 files:

```bash
ffmpeg -f mjpeg -i http://<device_ip>:81/stream -r 15 -c:v libx264 -b:v 1500k \
  -f segment -segment_time 60 -reset_timestamps 1 out_%03d.mp4
```

### Option B — Nginx‑RTMP to HLS

`nginx.conf` minimal example on the server:

```nginx
rtmp {
  server {
    listen 1935;
    application live {
      live on;
      hls on;
      hls_path /var/www/hls;
      hls_fragment 2s;
    }
  }
}
```

Then push with FFmpeg (see Option A) to `rtmp://<server>/live/stream` and serve `.m3u8` from `/var/www/hls` via HTTP.

### Option C — Push frames from ESP32 (HTTP POST)

If you need the ESP32 to push frames to your API, you can POST JPEG frames periodically. Keep intervals modest (e.g., 200–500 ms) to avoid overload.

```cpp
#include "esp_camera.h"
#include "esp_http_client.h"

static const char* upload_url = "http://<server>/upload";

void send_frame_http() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return;

  esp_http_client_config_t cfg = { .url = upload_url, .timeout_ms = 5000 };
  esp_http_client_handle_t client = esp_http_client_init(&cfg);
  esp_http_client_set_method(client, HTTP_METHOD_POST);
  esp_http_client_set_header(client, "Content-Type", "image/jpeg");
  esp_http_client_set_post_field(client, (const char*)fb->buf, fb->len);
  esp_http_client_perform(client);
  esp_http_client_cleanup(client);
  esp_camera_fb_return(fb);
}
```

Server‑side, implement `/upload` to ingest or re‑publish (RTMP/HLS/WebRTC). For most use‑cases, pulling with FFmpeg and re‑streaming is simpler and more reliable.

## Process with Google Cloud Vision (server example)

This repo includes a minimal Python script that pulls the ESP32‑CAM MJPEG and sends sampled frames to Google Cloud Vision for label detection.

### Setup

1. Create a Google Cloud project and enable "Vision API".
2. Create a service account and download its JSON key.
3. Place the key file on your machine and set:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/your-key.json
```

### Install and run

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Point to your ESP stream URL
export ESP_STREAM_URL=http://<device_ip>:81/stream
# Optional: how often to sample frames (seconds)
export SAMPLE_EVERY_SECONDS=2.0

python server.py
```

You should see top labels printed every few seconds, e.g.: `Labels: person (0.98), bicycle (0.76), ...`.
