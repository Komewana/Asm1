#include <esp_now.h>
#include <WiFi.h>
#include <ESP32Servo.h>

#include <Wire.h>
#include "RTClib.h"

// ===== WiFi để lock channel (PHẢI giống ESP32-CAM) =====
const char* WIFI_SSID = "hhh";
const char* WIFI_PASS = "12345678";

// ===== MAC ESP32-CAM (STA MAC) =====
uint8_t camAddress[] = {0xD4, 0xE9, 0xF4, 0xB3, 0xF9, 0xC8};

// ===== Pins =====
#define IR_PIN     12      // OUT của cảm biến IR
#define SERVO_PIN  13
#define LED_PIN    14      // ✅ LED báo có vật thể (chọn GPIO trống)

// ===== I2C (HW-084 / DS3231) =====
#define SDA_PIN 15
#define SCL_PIN 2

// Nếu module của bạn: phát hiện vật thể -> OUT = LOW  => để LOW (hay gặp)
// Nếu phát hiện vật thể -> OUT = HIGH => đổi thành HIGH
const int IR_ACTIVE_LEVEL = LOW;

// Debounce chống nhiễu
const uint32_t DEBOUNCE_MS = 60;

Servo myServo;
esp_now_peer_info_t peerInfo;

bool vatTheDangOTrong = false;
int lastIrState = HIGH;
uint32_t lastChangeMs = 0;

// ===== RTC (HW-084 DS3231) =====
RTC_DS3231 rtc;

// ✅ Send callback (core mới)
void onSent(const wifi_tx_info_t* info, esp_now_send_status_t status) {
  Serial.print("ESP-NOW send: ");
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "SUCCESS" : "FAIL");
}

// tạo timestamp "YYYYMMDD_HHMMSS"
String getTimestamp() {
  DateTime now = rtc.now();
  char ts[32];
  snprintf(ts, sizeof(ts), "%04d%02d%02d_%02d%02d%02d",
           now.year(), now.month(), now.day(),
           now.hour(), now.minute(), now.second());
  return String(ts);
}

void addPeerLockedChannel() {
  int ch = WiFi.channel();
  Serial.print("DevKit channel lock = ");
  Serial.println(ch);

  // Xóa peer cũ nếu có
  esp_now_del_peer(camAddress);

  memset(&peerInfo, 0, sizeof(peerInfo));
  memcpy(peerInfo.peer_addr, camAddress, 6);
  peerInfo.channel = ch;      // ⭐ quan trọng
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("❌ Add peer failed");
  } else {
    Serial.println("✅ Peer added OK");
  }
}

void guiLenhChupAnh() {
  // gửi kèm timestamp
  String payload = "CHUP|" + getTimestamp();
  esp_err_t result = esp_now_send(camAddress, (uint8_t*)payload.c_str(), payload.length());

  if (result == ESP_OK) Serial.println(">> esp_now_send(): " + payload);
  else Serial.println(">> esp_now_send() ERROR");
}

bool irDetectedDebounced() {
  int cur = digitalRead(IR_PIN);

  if (cur != lastIrState) {
    lastIrState = cur;
    lastChangeMs = millis();
  }

  if (millis() - lastChangeMs >= DEBOUNCE_MS) {
    return (lastIrState == IR_ACTIVE_LEVEL);
  }
  return vatTheDangOTrong; // giữ trạng thái cũ để tránh giật
}

void setupRTC() {
  // ✅ khai báo SDA/SCL theo kiểu bạn muốn
  Wire.begin(SDA_PIN, SCL_PIN);

  if (!rtc.begin()) {
    Serial.println("❌ DS3231 not found! (HW-084)");
    return;
  }

  Serial.println("✅ DS3231 OK");

  // Nếu RTC mất nguồn (pin yếu / tháo pin) thì set theo thời điểm compile
  if (rtc.lostPower()) {
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    Serial.println("⚠️ RTC lost power -> set to compile time");
  }

  Serial.println("RTC time: " + getTimestamp());
}

void setup() {
  Serial.begin(115200);

  myServo.attach(SERVO_PIN, 500, 2400);
  myServo.write(0);

  pinMode(IR_PIN, INPUT_PULLUP);

  // ✅ LED init
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); // mặc định tắt

  // ===== RTC init =====
  setupRTC();

  // 1) Join WiFi trước để lock channel
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("DevKit connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
    Serial.print(".");
  }
  Serial.println("\n✅ DevKit WiFi connected");
  Serial.print("DevKit MAC: "); Serial.println(WiFi.macAddress());

  // 2) Init ESP-NOW sau khi WiFi ổn
  if (esp_now_init() != ESP_OK) {
    Serial.println("❌ ESP-NOW init failed");
    return;
  }
  esp_now_register_send_cb(onSent);

  // 3) Add peer đúng channel
  addPeerLockedChannel();

  // init debounce state
  lastIrState = digitalRead(IR_PIN);
  lastChangeMs = millis();

  Serial.println("🚀 DevKit READY!");
  Serial.print("IR_ACTIVE_LEVEL = ");
  Serial.println(IR_ACTIVE_LEVEL == LOW ? "LOW (detect)" : "HIGH (detect)");
}

void loop() {
  bool detected = irDetectedDebounced();

  if (detected) {
    // ✅ BẬT LED khi có vật thể
    digitalWrite(LED_PIN, HIGH);

    if (!vatTheDangOTrong) {
      Serial.println("PHAT HIEN VAT THE (IR)! -> gui CHUP 1 lan");
      guiLenhChupAnh();
      delay(200);
      myServo.write(180);
      vatTheDangOTrong = true;
    }
  } else {
    // ✅ TẮT LED khi không có vật thể
    digitalWrite(LED_PIN, LOW);

    if (vatTheDangOTrong) {
      Serial.println("Vat the di ra -> reset");
      myServo.write(0);
      delay(500);
      vatTheDangOTrong = false;
    }
  }

  delay(20);
}
