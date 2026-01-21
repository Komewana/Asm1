#include "esp_camera.h"
#include "FS.h"
#include "SD_MMC.h"
#include <WiFi.h>

// =====================
// 1) CẤU HÌNH
// =====================
const char* ssid = "hhh";
const char* password = "12345678";

// ---- SERVER (HTTP) ----
const char* HOST = "visiondrinksurvey.duckdns.org"; // hoặc IP public
const int   PORT = 5000;
const char* PATH = "/api/upload_cam";

// 5 giây chụp 1 ảnh (LUÔN CHỤP DÙ CÓ WIFI HAY KHÔNG)
static const uint32_t CAPTURE_INTERVAL_MS = 5000;

// =====================
// 2) PIN MAPPING (AI THINKER)
// =====================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

static uint32_t lastCaptureMs = 0;

// =====================
// Upload multipart (HTTP)
// =====================
bool uploadFileMultipartHTTP(File &file) {
  WiFiClient client;

  if (!client.connect(HOST, PORT)) {
    Serial.println("❌ Khong ket noi duoc toi server");
    return false;
  }

  String boundary = "----ESP32FormBoundary";
  String head =
    "--" + boundary + "\r\n"
    "Content-Disposition: form-data; name=\"file\"; filename=\"cam.jpg\"\r\n"
    "Content-Type: image/jpeg\r\n\r\n";
  String tail = "\r\n--" + boundary + "--\r\n";

  uint32_t contentLength = head.length() + file.size() + tail.length();

  // HTTP header
  client.print(String("POST ") + PATH + " HTTP/1.1\r\n");
  client.print(String("Host: ") + HOST + "\r\n");
  client.print("Connection: close\r\n");
  client.print("Content-Type: multipart/form-data; boundary=" + boundary + "\r\n");
  client.print("Content-Length: " + String(contentLength) + "\r\n\r\n");

  // Body
  client.print(head);

  uint8_t buf[1024];
  while (file.available()) {
    size_t n = file.read(buf, sizeof(buf));
    client.write(buf, n);
  }

  client.print(tail);

  // Đọc status line
  String statusLine = "";
  unsigned long t0 = millis();
  while (client.connected() && millis() - t0 < 8000) {
    while (client.available()) {
      String line = client.readStringUntil('\n');
      line.trim();
      if (line.startsWith("HTTP/1.1")) {
        statusLine = line;
        Serial.println("Server: " + statusLine);
      }
    }
  }

  client.stop();
  return statusLine.indexOf("200") >= 0 || statusLine.indexOf("201") >= 0;
}

// =====================
// WiFi: không block (tự reconnect nền)
// =====================
void ensureWiFi() {
  static uint32_t lastTry = 0;

  if (WiFi.status() == WL_CONNECTED) return;

  // 3 giây thử connect lại 1 lần (không while chờ)
  if (millis() - lastTry < 3000) return;
  lastTry = millis();

  Serial.println("📶 WiFi not connected -> trying reconnect...");
  WiFi.disconnect();
  WiFi.begin(ssid, password);
}

// =====================
// Capture -> Save SD
// =====================
String captureToSD() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Capture failed");
    return "";
  }

  // đặt tên file
  String path = "/img_" + String(millis()) + ".jpg";

  File f = SD_MMC.open(path.c_str(), FILE_WRITE);
  if (!f) {
    Serial.println("❌ Open file write failed");
    esp_camera_fb_return(fb);
    return "";
  }

  f.write(fb->buf, fb->len);
  f.close();
  esp_camera_fb_return(fb);

  Serial.print("✅ Saved: ");
  Serial.println(path);
  return path;
}

// =====================
// Try upload (chỉ khi có WiFi)
// =====================
void tryUploadAndMaybeDelete(const String &path) {
  if (path.length() == 0) return;

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ No WiFi -> skip upload (keep file on SD)");
    return;
  }

  File rf = SD_MMC.open(path.c_str(), FILE_READ);
  if (!rf) {
    Serial.println("❌ Open file read failed");
    return;
  }

  Serial.print("⬆️ Uploading: ");
  Serial.println(path);

  bool ok = uploadFileMultipartHTTP(rf);
  rf.close();

  if (ok) {
    Serial.println("✅ Upload OK -> delete file");
    SD_MMC.remove(path.c_str());
  } else {
    Serial.println("❌ Upload FAIL -> keep file");
  }
}

// =====================
// SETUP
// =====================
void setup() {
  Serial.begin(115200);
  delay(500);

  // WiFi (khởi động connect nhưng KHÔNG CHỜ)
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.println("\n📶 Starting WiFi (non-blocking)...");

  // Camera
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  } else {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("❌ Camera init failed");
    return;
  }
  Serial.println("✅ Camera OK");

  // Xoay 180°: vflip + hmirror
  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 1);
    s->set_hmirror(s, 0);
    Serial.println("✅ Applied rotation 180° (vflip=1, hmirror=1)");
  }

  // SD Card
  if (!SD_MMC.begin("/sdcard", true)) {
    Serial.println("❌ SD Card Mount Failed");
    return;
  }
  if (SD_MMC.cardType() == CARD_NONE) {
    Serial.println("❌ No SD Card");
    return;
  }
  Serial.println("✅ SD Card OK");

  lastCaptureMs = millis(); // bắt đầu đếm từ lúc setup xong
}

// =====================
// LOOP
// =====================
void loop() {
  ensureWiFi(); // WiFi tự reconnect nền, không block

  uint32_t now = millis();
  if (now - lastCaptureMs >= CAPTURE_INTERVAL_MS) {
    lastCaptureMs = now;

    // 1) luôn chụp + lưu SD
    String path = captureToSD();

    // 2) nếu có WiFi thì thử upload (fail thì giữ file)
    tryUploadAndMaybeDelete(path);
  }

  delay(20);
}
