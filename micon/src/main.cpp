#include <Arduino.h>
#include <WiFi.h>

#include "esp_camera.h"
#include "esp_idf_version.h"
#include "esp_http_server.h"

#if __has_include("ESP_I2S.h")
#include "ESP_I2S.h"
#define USE_ESP_I2S_API 1
#else
#include <I2S.h>
#define USE_ESP_I2S_API 0
#endif

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "camera_pins.h"

// config.h is intentionally local and ignored by git. The fallback values
// keep the project source-readable before a device-specific config is copied.
#if __has_include("config.h")
#include "config.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif

#ifndef CAMERA_ID
#define CAMERA_ID "demo-camera-1"
#endif

#ifndef CAMERA_HTTP_PORT
#define CAMERA_HTTP_PORT 80
#endif

#ifndef CAMERA_FRAME_SIZE
#define CAMERA_FRAME_SIZE FRAMESIZE_SVGA
#endif

#ifndef CAMERA_JPEG_QUALITY
#define CAMERA_JPEG_QUALITY 8
#endif

#ifndef CAMERA_MAX_FPS
#define CAMERA_MAX_FPS 15
#endif

#ifndef AUDIO_HTTP_PORT
#define AUDIO_HTTP_PORT 81
#endif

#ifndef SOUND_CALIBRATION_MS
#define SOUND_CALIBRATION_MS 2000
#endif

#ifndef SOUND_AMBIENT_ALPHA
#define SOUND_AMBIENT_ALPHA 0.02f
#endif

#ifndef SOUND_TRIGGER_RATIO
#define SOUND_TRIGGER_RATIO 3.0f
#endif

#ifndef SOUND_TRIGGER_DEVIATIONS
#define SOUND_TRIGGER_DEVIATIONS 6.0f
#endif

#ifndef SOUND_RELEASE_RATIO
#define SOUND_RELEASE_RATIO 1.5f
#endif

#ifndef SOUND_RELEASE_FRAMES
#define SOUND_RELEASE_FRAMES 3
#endif

#ifndef SOUND_COOLDOWN_MS
#define SOUND_COOLDOWN_MS 300
#endif

#ifndef CAMERA_USE_STATIC_IP
#define CAMERA_USE_STATIC_IP 0
#endif

#ifndef CAMERA_STATIC_IP
#define CAMERA_STATIC_IP ""
#endif

#ifndef CAMERA_GATEWAY
#define CAMERA_GATEWAY ""
#endif

#ifndef CAMERA_SUBNET
#define CAMERA_SUBNET ""
#endif

#ifndef CAMERA_PRIMARY_DNS
#define CAMERA_PRIMARY_DNS ""
#endif

#ifndef CAMERA_SECONDARY_DNS
#define CAMERA_SECONDARY_DNS ""
#endif

namespace {

constexpr uint32_t SERIAL_BAUD_RATE = 115200;
constexpr uint32_t WIFI_RECONNECT_INTERVAL_MS = 5000;
constexpr uint32_t CAMERA_CAPTURE_TIMEOUT_MS = 1000;
static_assert(CAMERA_MAX_FPS > 0, "CAMERA_MAX_FPS must be positive");
static_assert(AUDIO_HTTP_PORT != CAMERA_HTTP_PORT,
              "audio and camera HTTP ports must differ");
static_assert(SOUND_CALIBRATION_MS > 0,
              "SOUND_CALIBRATION_MS must be positive");
static_assert(SOUND_AMBIENT_ALPHA > 0.0f && SOUND_AMBIENT_ALPHA <= 1.0f,
              "SOUND_AMBIENT_ALPHA must be in (0, 1]");
static_assert(SOUND_TRIGGER_RATIO > SOUND_RELEASE_RATIO,
              "sound release ratio must be below trigger ratio");
static_assert(SOUND_TRIGGER_DEVIATIONS > 0.0f,
              "SOUND_TRIGGER_DEVIATIONS must be positive");
static_assert(SOUND_RELEASE_FRAMES > 0,
              "SOUND_RELEASE_FRAMES must be positive");
constexpr uint32_t CAMERA_FRAME_INTERVAL_MS =
    (1000U + CAMERA_MAX_FPS - 1U) / CAMERA_MAX_FPS;
constexpr uint32_t MICROPHONE_SAMPLE_RATE_HZ = 16000;
constexpr size_t MICROPHONE_FRAME_SAMPLES = 320;
constexpr int MICROPHONE_DATA_PIN = 41;
constexpr int MICROPHONE_CLOCK_PIN = 42;
constexpr uint32_t SOUND_HEARTBEAT_INTERVAL_MS = 1000;

constexpr char STREAM_CONTENT_TYPE[] =
    "multipart/x-mixed-replace;boundary=frame";
constexpr char STREAM_BOUNDARY[] = "\r\n--frame\r\n";
constexpr char STREAM_PART[] =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t http_server = nullptr;
httpd_handle_t audio_http_server = nullptr;
SemaphoreHandle_t camera_mutex = nullptr;
uint32_t next_wifi_attempt_at = 0;
bool wifi_was_connected = false;

#if USE_ESP_I2S_API
I2SClass microphone_i2s;
#endif

portMUX_TYPE sound_event_mutex = portMUX_INITIALIZER_UNLOCKED;
volatile bool microphone_ready = false;
uint32_t sound_event_sequence = 0;
uint32_t sound_event_uptime_ms = 0;

struct SoundEventSnapshot {
  bool ready;
  uint32_t sequence;
  uint32_t uptime_ms;
};

SoundEventSnapshot soundEventSnapshot() {
  SoundEventSnapshot snapshot;
  portENTER_CRITICAL(&sound_event_mutex);
  snapshot.ready = microphone_ready;
  snapshot.sequence = sound_event_sequence;
  snapshot.uptime_ms = sound_event_uptime_ms;
  portEXIT_CRITICAL(&sound_event_mutex);
  return snapshot;
}

void publishSoundEvent() {
  portENTER_CRITICAL(&sound_event_mutex);
  ++sound_event_sequence;
  sound_event_uptime_ms = millis();
  portEXIT_CRITICAL(&sound_event_mutex);
}

void setMicrophoneReady(bool ready) {
  portENTER_CRITICAL(&sound_event_mutex);
  microphone_ready = ready;
  portEXIT_CRITICAL(&sound_event_mutex);
}

bool initMicrophone() {
#if USE_ESP_I2S_API
  microphone_i2s.setPinsPdmRx(MICROPHONE_CLOCK_PIN, MICROPHONE_DATA_PIN);
  return microphone_i2s.begin(I2S_MODE_PDM_RX, MICROPHONE_SAMPLE_RATE_HZ,
                              I2S_DATA_BIT_WIDTH_16BIT,
                              I2S_SLOT_MODE_MONO);
#else
  I2S.setAllPins(-1, MICROPHONE_CLOCK_PIN, MICROPHONE_DATA_PIN, -1, -1);
  return I2S.begin(PDM_MONO_MODE, MICROPHONE_SAMPLE_RATE_HZ, 16);
#endif
}

size_t readMicrophoneSamples(int16_t *samples, size_t sample_count) {
  const size_t bytes_needed = sample_count * sizeof(int16_t);
  size_t bytes_read = 0;
  uint8_t *destination = reinterpret_cast<uint8_t *>(samples);

  while (bytes_read < bytes_needed) {
#if USE_ESP_I2S_API
    const size_t chunk = microphone_i2s.readBytes(
        reinterpret_cast<char *>(destination + bytes_read),
        bytes_needed - bytes_read);
#else
    const int result = I2S.read(destination + bytes_read,
                                bytes_needed - bytes_read);
    const size_t chunk = result > 0 ? static_cast<size_t>(result) : 0;
#endif
    if (chunk == 0) {
      break;
    }
    bytes_read += chunk;
  }
  return bytes_read / sizeof(int16_t);
}

float frameSoundLevel(const int16_t *samples, size_t sample_count) {
  int64_t sum = 0;
  for (size_t index = 0; index < sample_count; ++index) {
    sum += samples[index];
  }
  const int32_t mean = static_cast<int32_t>(sum / sample_count);

  uint64_t absolute_sum = 0;
  for (size_t index = 0; index < sample_count; ++index) {
    const int32_t centered = static_cast<int32_t>(samples[index]) - mean;
    absolute_sum += static_cast<uint32_t>(abs(centered));
  }
  return static_cast<float>(absolute_sum) / sample_count;
}

void microphoneTask(void *) {
  int16_t samples[MICROPHONE_FRAME_SAMPLES];
  const uint32_t calibration_started_at = millis();
  float ambient_level = 0.0f;
  float ambient_deviation = 0.0f;
  uint32_t calibration_frames = 0;
  uint32_t last_event_at = 0;
  uint32_t release_frames = 0;
  uint32_t consecutive_read_failures = 0;
  bool calibrated = false;
  bool latched = false;

  while (true) {
    const size_t samples_read =
        readMicrophoneSamples(samples, MICROPHONE_FRAME_SAMPLES);
    if (samples_read != MICROPHONE_FRAME_SAMPLES) {
      ++consecutive_read_failures;
      setMicrophoneReady(false);
      if (consecutive_read_failures == 1 ||
          consecutive_read_failures % 10 == 0) {
        Serial.printf("Microphone read failed; retrying (%lu)\n",
                      static_cast<unsigned long>(
                          consecutive_read_failures));
      }
      vTaskDelay(pdMS_TO_TICKS(20));
      continue;
    }

    if (consecutive_read_failures > 0) {
      Serial.printf("Microphone read recovered after %lu failures\n",
                    static_cast<unsigned long>(
                        consecutive_read_failures));
      consecutive_read_failures = 0;
      if (calibrated) {
        setMicrophoneReady(true);
      }
    }

    const float level = frameSoundLevel(samples, samples_read);
    if (!calibrated) {
      ++calibration_frames;
      const float delta = level - ambient_level;
      ambient_level += delta / calibration_frames;
      ambient_deviation +=
          (fabsf(delta) - ambient_deviation) / calibration_frames;
      if (millis() - calibration_started_at >= SOUND_CALIBRATION_MS) {
        calibrated = true;
        setMicrophoneReady(true);
        Serial.println("Microphone ambient calibration complete");
      }
      continue;
    }

    const float trigger_level =
        max(1.0f,
            max(ambient_level * SOUND_TRIGGER_RATIO,
                ambient_level +
                    ambient_deviation * SOUND_TRIGGER_DEVIATIONS));
    const float release_level = ambient_level * SOUND_RELEASE_RATIO;
    const uint32_t now = millis();

    if (!latched && level >= trigger_level &&
        now - last_event_at >= SOUND_COOLDOWN_MS) {
      publishSoundEvent();
      last_event_at = now;
      latched = true;
      release_frames = 0;
      continue;
    }

    if (latched) {
      if (level <= release_level) {
        ++release_frames;
        if (release_frames >= SOUND_RELEASE_FRAMES) {
          latched = false;
          release_frames = 0;
        }
      } else {
        release_frames = 0;
      }
      continue;
    }

    const float delta = level - ambient_level;
    ambient_level += SOUND_AMBIENT_ALPHA * delta;
    ambient_deviation +=
        SOUND_AMBIENT_ALPHA * (fabsf(delta) - ambient_deviation);
  }
}

void setJsonHeaders(httpd_req_t *request) {
  httpd_resp_set_type(request, "application/json");
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
}

bool takeCameraFrame(camera_fb_t **frame) {
  if (camera_mutex == nullptr ||
      xSemaphoreTake(camera_mutex,
                     pdMS_TO_TICKS(CAMERA_CAPTURE_TIMEOUT_MS)) != pdTRUE) {
    return false;
  }

  *frame = esp_camera_fb_get();
  if (*frame == nullptr) {
    xSemaphoreGive(camera_mutex);
    return false;
  }

  return true;
}

void releaseCameraFrame(camera_fb_t *frame) {
  if (frame != nullptr) {
    esp_camera_fb_return(frame);
  }
  if (camera_mutex != nullptr) {
    xSemaphoreGive(camera_mutex);
  }
}

esp_err_t rootHandler(httpd_req_t *request) {
  static const char body_template[] =
      "smart-home-camera\n"
      "GET /stream for MJPEG\n"
      "GET /snapshot for one JPEG\n"
      "GET /health for status\n"
      "GET http://<camera-ip>:%u/sound-events for sound events\n";
  char body[256];
  snprintf(body, sizeof(body), body_template,
           static_cast<unsigned>(AUDIO_HTTP_PORT));
  httpd_resp_set_type(request, "text/plain; charset=utf-8");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  return httpd_resp_send(request, body, HTTPD_RESP_USE_STRLEN);
}

esp_err_t healthHandler(httpd_req_t *request) {
  const bool connected = WiFi.status() == WL_CONNECTED;
  const String ip = connected ? WiFi.localIP().toString() : "";
  const SoundEventSnapshot sound = soundEventSnapshot();
  char body[512];

  snprintf(body, sizeof(body),
           "{\"status\":\"ok\",\"camera_id\":\"%s\","
           "\"wifi_connected\":%s,\"ip\":\"%s\","
           "\"uptime_ms\":%lu,\"camera_max_fps\":%u,"
           "\"microphone_ready\":%s,\"audio_http_port\":%u}",
           CAMERA_ID, connected ? "true" : "false", ip.c_str(),
           static_cast<unsigned long>(millis()),
           static_cast<unsigned>(CAMERA_MAX_FPS),
           sound.ready ? "true" : "false",
           static_cast<unsigned>(AUDIO_HTTP_PORT));

  setJsonHeaders(request);
  return httpd_resp_send(request, body, HTTPD_RESP_USE_STRLEN);
}

esp_err_t snapshotHandler(httpd_req_t *request) {
  camera_fb_t *frame = nullptr;
  if (!takeCameraFrame(&frame)) {
    httpd_resp_send_500(request);
    return ESP_FAIL;
  }

  uint8_t *jpeg_buffer = frame->buf;
  size_t jpeg_length = frame->len;
  bool allocated_jpeg = false;

  if (frame->format != PIXFORMAT_JPEG) {
    if (!frame2jpg(frame, 80, &jpeg_buffer, &jpeg_length)) {
      releaseCameraFrame(frame);
      httpd_resp_send_500(request);
      return ESP_FAIL;
    }
    allocated_jpeg = true;
  }

  httpd_resp_set_type(request, "image/jpeg");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  const esp_err_t result = httpd_resp_send(
      request, reinterpret_cast<const char *>(jpeg_buffer), jpeg_length);

  if (allocated_jpeg) {
    free(jpeg_buffer);
  }
  releaseCameraFrame(frame);
  return result;
}

esp_err_t streamHandler(httpd_req_t *request) {
  // The MVP has one Python consumer per camera. Holding this mutex for the
  // lifetime of the stream prevents a second client from starving frames.
  if (camera_mutex == nullptr ||
      xSemaphoreTake(camera_mutex, portMAX_DELAY) != pdTRUE) {
    httpd_resp_set_status(request, "503 Service Unavailable");
    return httpd_resp_send(request, "camera busy", HTTPD_RESP_USE_STRLEN);
  }

  httpd_resp_set_type(request, STREAM_CONTENT_TYPE);
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");

  esp_err_t result = ESP_OK;
  char part_header[96];
  uint32_t next_frame_at = millis();

  while (result == ESP_OK) {
    const int32_t wait_ms = static_cast<int32_t>(next_frame_at - millis());
    if (wait_ms > 0) {
      vTaskDelay(pdMS_TO_TICKS(wait_ms));
    }
    next_frame_at = millis() + CAMERA_FRAME_INTERVAL_MS;

    camera_fb_t *frame = esp_camera_fb_get();
    if (frame == nullptr) {
      result = ESP_FAIL;
      break;
    }

    uint8_t *jpeg_buffer = frame->buf;
    size_t jpeg_length = frame->len;
    bool allocated_jpeg = false;

    if (frame->format != PIXFORMAT_JPEG) {
      if (!frame2jpg(frame, 80, &jpeg_buffer, &jpeg_length)) {
        esp_camera_fb_return(frame);
        result = ESP_FAIL;
        break;
      }
      allocated_jpeg = true;
    }

    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(request, STREAM_BOUNDARY,
                                     strlen(STREAM_BOUNDARY));
    }

    if (result == ESP_OK) {
      const int header_length =
          snprintf(part_header, sizeof(part_header), STREAM_PART,
                   static_cast<unsigned>(jpeg_length));
      if (header_length < 0 ||
          header_length >= static_cast<int>(sizeof(part_header))) {
        result = ESP_FAIL;
      } else {
        result = httpd_resp_send_chunk(request, part_header, header_length);
      }
    }

    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(
          request, reinterpret_cast<const char *>(jpeg_buffer), jpeg_length);
    }

    if (allocated_jpeg) {
      free(jpeg_buffer);
    }
    esp_camera_fb_return(frame);

    // Give the HTTP task and Wi-Fi stack a chance to run between frames.
    vTaskDelay(pdMS_TO_TICKS(1));
  }

  // Complete the chunked response when the client disconnects or capture
  // fails. The return value is intentionally ignored during cleanup.
  httpd_resp_send_chunk(request, nullptr, 0);
  xSemaphoreGive(camera_mutex);
  return result;
}

esp_err_t soundEventsHandler(httpd_req_t *request) {
  httpd_resp_set_type(request, "application/x-ndjson; charset=utf-8");
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");

  SoundEventSnapshot snapshot = soundEventSnapshot();
  if (!snapshot.ready) {
    httpd_resp_set_status(request, "503 Service Unavailable");
    return httpd_resp_send(request, "microphone unavailable\n",
                           HTTPD_RESP_USE_STRLEN);
  }

  // Events that happened before this connection are deliberately not replayed.
  uint32_t last_sent_sequence = snapshot.sequence;
  uint32_t last_heartbeat_at = 0;
  esp_err_t result = ESP_OK;
  char body[128];

  while (result == ESP_OK) {
    snapshot = soundEventSnapshot();
    if (!snapshot.ready) {
      break;
    }

    if (snapshot.sequence != last_sent_sequence) {
      const int length = snprintf(
          body, sizeof(body),
          "{\"type\":\"sound\",\"sequence\":%lu,\"uptime_ms\":%lu}\n",
          static_cast<unsigned long>(snapshot.sequence),
          static_cast<unsigned long>(snapshot.uptime_ms));
      result = httpd_resp_send_chunk(request, body, length);
      last_sent_sequence = snapshot.sequence;
    }

    const uint32_t now = millis();
    if (result == ESP_OK &&
        now - last_heartbeat_at >= SOUND_HEARTBEAT_INTERVAL_MS) {
      const int length = snprintf(
          body, sizeof(body),
          "{\"type\":\"heartbeat\",\"uptime_ms\":%lu}\n",
          static_cast<unsigned long>(now));
      result = httpd_resp_send_chunk(request, body, length);
      last_heartbeat_at = now;
    }

    vTaskDelay(pdMS_TO_TICKS(20));
  }

  httpd_resp_send_chunk(request, nullptr, 0);
  return result;
}

bool startHttpServer() {
  httpd_config_t server_config = HTTPD_DEFAULT_CONFIG();
  server_config.server_port = CAMERA_HTTP_PORT;
  server_config.max_uri_handlers = 4;
  server_config.max_open_sockets = 4;
  server_config.stack_size = 8192;
  server_config.lru_purge_enable = true;

  if (httpd_start(&http_server, &server_config) != ESP_OK) {
    Serial.println("HTTP server start failed");
    return false;
  }

  static const httpd_uri_t root_uri = {
      .uri = "/",
      .method = HTTP_GET,
      .handler = rootHandler,
      .user_ctx = nullptr,
  };
  static const httpd_uri_t health_uri = {
      .uri = "/health",
      .method = HTTP_GET,
      .handler = healthHandler,
      .user_ctx = nullptr,
  };
  static const httpd_uri_t snapshot_uri = {
      .uri = "/snapshot",
      .method = HTTP_GET,
      .handler = snapshotHandler,
      .user_ctx = nullptr,
  };
  static const httpd_uri_t stream_uri = {
      .uri = "/stream",
      .method = HTTP_GET,
      .handler = streamHandler,
      .user_ctx = nullptr,
  };

  httpd_register_uri_handler(http_server, &root_uri);
  httpd_register_uri_handler(http_server, &health_uri);
  httpd_register_uri_handler(http_server, &snapshot_uri);
  httpd_register_uri_handler(http_server, &stream_uri);

  return true;
}

bool startAudioHttpServer() {
  httpd_config_t server_config = HTTPD_DEFAULT_CONFIG();
  server_config.server_port = AUDIO_HTTP_PORT;
  server_config.ctrl_port += 1;
  server_config.max_uri_handlers = 1;
  server_config.max_open_sockets = 4;
  server_config.stack_size = 6144;
  server_config.lru_purge_enable = true;

  if (httpd_start(&audio_http_server, &server_config) != ESP_OK) {
    Serial.println("Audio HTTP server start failed");
    return false;
  }

  static const httpd_uri_t sound_events_uri = {
      .uri = "/sound-events",
      .method = HTTP_GET,
      .handler = soundEventsHandler,
      .user_ctx = nullptr,
  };
  if (httpd_register_uri_handler(audio_http_server,
                                 &sound_events_uri) != ESP_OK) {
    httpd_stop(audio_http_server);
    audio_http_server = nullptr;
    Serial.println("Sound event handler registration failed");
    return false;
  }
  return true;
}

bool initCamera() {
  camera_config_t camera_config = {};
  camera_config.ledc_channel = LEDC_CHANNEL_0;
  camera_config.ledc_timer = LEDC_TIMER_0;
  camera_config.pin_d0 = Y2_GPIO_NUM;
  camera_config.pin_d1 = Y3_GPIO_NUM;
  camera_config.pin_d2 = Y4_GPIO_NUM;
  camera_config.pin_d3 = Y5_GPIO_NUM;
  camera_config.pin_d4 = Y6_GPIO_NUM;
  camera_config.pin_d5 = Y7_GPIO_NUM;
  camera_config.pin_d6 = Y8_GPIO_NUM;
  camera_config.pin_d7 = Y9_GPIO_NUM;
  camera_config.pin_xclk = XCLK_GPIO_NUM;
  camera_config.pin_pclk = PCLK_GPIO_NUM;
  camera_config.pin_vsync = VSYNC_GPIO_NUM;
  camera_config.pin_href = HREF_GPIO_NUM;

  // ESP32 Arduino 3.x uses the SCCB spelling; Arduino 2.x used SSCB.
#if ESP_IDF_VERSION_MAJOR >= 5
  camera_config.pin_sccb_sda = SIOD_GPIO_NUM;
  camera_config.pin_sccb_scl = SIOC_GPIO_NUM;
#else
  camera_config.pin_sscb_sda = SIOD_GPIO_NUM;
  camera_config.pin_sscb_scl = SIOC_GPIO_NUM;
#endif

  camera_config.pin_pwdn = PWDN_GPIO_NUM;
  camera_config.pin_reset = RESET_GPIO_NUM;
  camera_config.xclk_freq_hz = 20000000;
  camera_config.pixel_format = PIXFORMAT_JPEG;
  camera_config.frame_size = CAMERA_FRAME_SIZE;
  camera_config.jpeg_quality = CAMERA_JPEG_QUALITY;

  if (psramFound()) {
    camera_config.fb_location = CAMERA_FB_IN_PSRAM;
    camera_config.fb_count = 2;
    camera_config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    // QVGA plus one DRAM buffer is a safe fallback for an incorrectly
    // configured board package or a board without working PSRAM.
    camera_config.fb_location = CAMERA_FB_IN_DRAM;
    camera_config.fb_count = 1;
    camera_config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    camera_config.frame_size = FRAMESIZE_QVGA;
  }

  const esp_err_t result = esp_camera_init(&camera_config);
  if (result != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", result);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor != nullptr && sensor->id.PID == OV3660_PID) {
    sensor->set_vflip(sensor, 1);
    sensor->set_brightness(sensor, 1);
    sensor->set_saturation(sensor, -2);
  }

  Serial.printf("Camera ready: frame_size=%u, jpeg_quality=%u, PSRAM=%s\n",
                static_cast<unsigned>(camera_config.frame_size),
                static_cast<unsigned>(camera_config.jpeg_quality),
                psramFound() ? "yes" : "no");
  return true;
}

void beginWifiConnection() {
  if (strcmp(WIFI_SSID, "YOUR_WIFI_SSID") == 0) {
    Serial.println("Set Wi-Fi credentials in micon/include/config.h");
  }

  Serial.printf("Connecting to Wi-Fi: %s\n", WIFI_SSID);
  WiFi.disconnect(false, false);

#if CAMERA_USE_STATIC_IP
  IPAddress local_ip;
  IPAddress gateway;
  IPAddress subnet;
  IPAddress primary_dns;
  IPAddress secondary_dns;
  const bool valid_static_ip =
      local_ip.fromString(CAMERA_STATIC_IP) &&
      gateway.fromString(CAMERA_GATEWAY) &&
      subnet.fromString(CAMERA_SUBNET) &&
      primary_dns.fromString(CAMERA_PRIMARY_DNS) &&
      secondary_dns.fromString(CAMERA_SECONDARY_DNS);

  if (!valid_static_ip) {
    Serial.println("Invalid static Wi-Fi configuration; retrying");
    next_wifi_attempt_at = millis() + WIFI_RECONNECT_INTERVAL_MS;
    return;
  }

  if (!WiFi.config(local_ip, gateway, subnet, primary_dns, secondary_dns)) {
    Serial.println("Static Wi-Fi configuration failed; retrying");
    next_wifi_attempt_at = millis() + WIFI_RECONNECT_INTERVAL_MS;
    return;
  }

  Serial.printf("Using static Wi-Fi IP: %s\n",
                local_ip.toString().c_str());
#endif

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  next_wifi_attempt_at = millis() + WIFI_RECONNECT_INTERVAL_MS;
}

void maintainWifiConnection() {
  const bool connected = WiFi.status() == WL_CONNECTED;

  if (connected) {
    if (!wifi_was_connected) {
      Serial.printf("Wi-Fi connected, IP=%s\n",
                    WiFi.localIP().toString().c_str());
      wifi_was_connected = true;
    }
    return;
  }

  if (wifi_was_connected) {
    Serial.println("Wi-Fi disconnected; retrying");
    wifi_was_connected = false;
  }

  if (static_cast<int32_t>(millis() - next_wifi_attempt_at) >= 0) {
    beginWifiConnection();
  }
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(200);
  Serial.printf("\nSmart-home camera starting: %s\n", CAMERA_ID);

  camera_mutex = xSemaphoreCreateMutex();
  if (camera_mutex == nullptr || !initCamera()) {
    Serial.println("Fatal initialization error; restarting in 5 seconds");
    delay(5000);
    ESP.restart();
  }

  bool microphone_task_started = false;
  if (initMicrophone()) {
    if (xTaskCreate(microphoneTask, "microphone", 4096, nullptr, 2,
                    nullptr) != pdPASS) {
      Serial.println("Microphone task start failed; sound events disabled");
      setMicrophoneReady(false);
    } else {
      microphone_task_started = true;
      Serial.println("Microphone started: PDM mono 16000 Hz, 16 bit");
    }
  } else {
    Serial.println("Microphone init failed; camera will continue");
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setHostname(CAMERA_ID);
  beginWifiConnection();

  if (!startHttpServer()) {
    Serial.println("Fatal HTTP server error; restarting in 5 seconds");
    delay(5000);
    ESP.restart();
  }

  if (microphone_task_started && !startAudioHttpServer()) {
    Serial.println("Sound event delivery disabled; camera will continue");
  }

  Serial.printf("HTTP server listening on port %u\n",
                static_cast<unsigned>(CAMERA_HTTP_PORT));
  Serial.println("Endpoints: /stream /snapshot /health");
  if (audio_http_server != nullptr) {
    Serial.printf("Sound event server listening on port %u: /sound-events\n",
                  static_cast<unsigned>(AUDIO_HTTP_PORT));
  }
}

void loop() {
  maintainWifiConnection();
  delay(50);
}
