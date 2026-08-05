#include <Arduino.h>
#include <WiFi.h>

#include "esp_camera.h"
#include "esp_idf_version.h"
#include "esp_http_server.h"

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

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

namespace {

constexpr uint32_t SERIAL_BAUD_RATE = 115200;
constexpr uint32_t WIFI_RECONNECT_INTERVAL_MS = 5000;
constexpr uint32_t CAMERA_CAPTURE_TIMEOUT_MS = 1000;

constexpr char STREAM_CONTENT_TYPE[] =
    "multipart/x-mixed-replace;boundary=frame";
constexpr char STREAM_BOUNDARY[] = "\r\n--frame\r\n";
constexpr char STREAM_PART[] =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t http_server = nullptr;
SemaphoreHandle_t camera_mutex = nullptr;
uint32_t next_wifi_attempt_at = 0;
bool wifi_was_connected = false;

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
  static const char body[] =
      "smart-home-camera\n"
      "GET /stream for MJPEG\n"
      "GET /snapshot for one JPEG\n"
      "GET /health for status\n";
  httpd_resp_set_type(request, "text/plain; charset=utf-8");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  return httpd_resp_send(request, body, HTTPD_RESP_USE_STRLEN);
}

esp_err_t healthHandler(httpd_req_t *request) {
  const bool connected = WiFi.status() == WL_CONNECTED;
  const String ip = connected ? WiFi.localIP().toString() : "";
  char body[384];

  snprintf(body, sizeof(body),
           "{\"status\":\"ok\",\"camera_id\":\"%s\","
           "\"wifi_connected\":%s,\"ip\":\"%s\","
           "\"uptime_ms\":%lu}",
           CAMERA_ID, connected ? "true" : "false", ip.c_str(),
           static_cast<unsigned long>(millis()));

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

  while (result == ESP_OK) {
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
      const int header_length = snprintf(part_header, sizeof(part_header),
                                          STREAM_PART,
                                          static_cast<unsigned>(jpeg_length));
      result = httpd_resp_send_chunk(request, part_header, header_length);
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

  Serial.printf("Camera ready: %ux%u, PSRAM=%s\n",
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

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setHostname(CAMERA_ID);
  beginWifiConnection();

  if (!startHttpServer()) {
    Serial.println("Fatal HTTP server error; restarting in 5 seconds");
    delay(5000);
    ESP.restart();
  }

  Serial.printf("HTTP server listening on port %u\n",
                static_cast<unsigned>(CAMERA_HTTP_PORT));
  Serial.println("Endpoints: /stream /snapshot /health");
}

void loop() {
  maintainWifiConnection();
  delay(50);
}
