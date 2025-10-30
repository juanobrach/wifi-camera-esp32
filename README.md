# CameraWebServer (ESP32‑S CAM via Arduino UNO R3 bridge)

This project runs the ESP32 Camera Web Server example adapted for ESP32‑S‑CAM/ESP32‑CAM. It’s wired and flashed using an Arduino UNO R3 as a USB‑serial bridge.

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
