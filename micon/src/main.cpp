#include <Arduino.h>
#include <WiFi.h>
#include <WiFiServer.h>

#include "esp_camera.h"

#include <errno.h>
#include <lwip/sockets.h>
#include <new>

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

#ifndef CAMERA_MAX_HTTP_CLIENTS
#define CAMERA_MAX_HTTP_CLIENTS 4
#endif

#ifndef CAMERA_FRAME_STALE_TIMEOUT_MS
#define CAMERA_FRAME_STALE_TIMEOUT_MS 1000
#endif

#ifndef CAMERA_CAPTURE_WATCHDOG_TIMEOUT_MS
#define CAMERA_CAPTURE_WATCHDOG_TIMEOUT_MS 10000
#endif

#ifndef CAMERA_CAPTURE_STARTUP_DELAY_MS
#define CAMERA_CAPTURE_STARTUP_DELAY_MS 1000
#endif

#ifndef CAMERA_CLIENT_REQUEST_TIMEOUT_MS
#define CAMERA_CLIENT_REQUEST_TIMEOUT_MS 3000
#endif

#ifndef CAMERA_CLIENT_WRITE_TIMEOUT_MS
#define CAMERA_CLIENT_WRITE_TIMEOUT_MS 2000
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
constexpr uint32_t CAMERA_FRAME_WAIT_TIMEOUT_MS = 3000;
constexpr uint32_t CAMERA_FRAME_LOCK_TIMEOUT_MS = 20;
constexpr uint32_t CAMERA_CAPTURE_RETRY_DELAY_MS = 20;
constexpr uint32_t CAMERA_HTTP_TASK_STACK_SIZE = 4096;
constexpr uint32_t CAMERA_HTTP_TASK_PRIORITY = 2;
constexpr uint32_t CAMERA_CLIENT_TASK_STACK_SIZE = 4096;
constexpr uint32_t CAMERA_CLIENT_TASK_PRIORITY = 2;
constexpr uint32_t CAMERA_CAPTURE_TASK_STACK_SIZE = 6144;
constexpr uint32_t CAMERA_CAPTURE_TASK_PRIORITY = 3;
constexpr uint32_t CAMERA_CAPTURE_WATCHDOG_TASK_STACK_SIZE = 3072;
static_assert(CAMERA_MAX_FPS > 0, "CAMERA_MAX_FPS must be positive");
static_assert(CAMERA_MAX_HTTP_CLIENTS > 0,
              "CAMERA_MAX_HTTP_CLIENTS must be positive");
static_assert(CAMERA_FRAME_STALE_TIMEOUT_MS > 0,
              "CAMERA_FRAME_STALE_TIMEOUT_MS must be positive");
static_assert(CAMERA_CAPTURE_WATCHDOG_TIMEOUT_MS >
                  CAMERA_FRAME_STALE_TIMEOUT_MS,
              "camera watchdog must exceed frame stale timeout");
static_assert(CAMERA_CAPTURE_STARTUP_DELAY_MS >= 0,
              "CAMERA_CAPTURE_STARTUP_DELAY_MS must not be negative");
static_assert(CAMERA_CLIENT_REQUEST_TIMEOUT_MS > 0,
              "CAMERA_CLIENT_REQUEST_TIMEOUT_MS must be positive");
static_assert(CAMERA_CLIENT_WRITE_TIMEOUT_MS > 0,
              "CAMERA_CLIENT_WRITE_TIMEOUT_MS must be positive");
constexpr uint32_t CAMERA_FRAME_INTERVAL_MS =
    (1000U + CAMERA_MAX_FPS - 1U) / CAMERA_MAX_FPS;

constexpr char STREAM_CONTENT_TYPE[] =
    "multipart/x-mixed-replace;boundary=frame";
constexpr char STREAM_BOUNDARY[] = "\r\n--frame\r\n";
constexpr char STREAM_PART[] =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

WiFiServer camera_http_server(CAMERA_HTTP_PORT, CAMERA_MAX_HTTP_CLIENTS);
SemaphoreHandle_t camera_client_mutex = nullptr;
uint32_t active_camera_clients = 0;
SemaphoreHandle_t latest_frame_mutex = nullptr;
uint8_t *latest_jpeg_buffer = nullptr;
size_t latest_jpeg_capacity = 0;
size_t latest_jpeg_length = 0;
uint32_t latest_frame_sequence = 0;
uint32_t latest_frame_captured_at = 0;
uint32_t camera_capture_failures = 0;
volatile uint32_t camera_capture_heartbeat_at = 0;
uint32_t next_wifi_attempt_at = 0;
bool wifi_was_connected = false;

bool ensureBufferCapacity(uint8_t **buffer, size_t *capacity,
                          size_t required) {
  if (required <= *capacity) {
    return true;
  }

  uint8_t *resized = static_cast<uint8_t *>(realloc(*buffer, required));
  if (resized == nullptr) {
    return false;
  }

  *buffer = resized;
  *capacity = required;
  return true;
}

bool publishLatestFrame(const uint8_t *jpeg_buffer, size_t jpeg_length) {
  if (latest_frame_mutex == nullptr || jpeg_buffer == nullptr ||
      jpeg_length == 0 ||
      xSemaphoreTake(latest_frame_mutex,
                     pdMS_TO_TICKS(CAMERA_FRAME_LOCK_TIMEOUT_MS)) != pdTRUE) {
    return false;
  }

  const bool copied =
      ensureBufferCapacity(&latest_jpeg_buffer, &latest_jpeg_capacity,
                           jpeg_length);
  if (copied) {
    memcpy(latest_jpeg_buffer, jpeg_buffer, jpeg_length);
    latest_jpeg_length = jpeg_length;
    latest_frame_captured_at = millis();
    ++latest_frame_sequence;
  }

  xSemaphoreGive(latest_frame_mutex);
  return copied;
}

bool latestFrameFreshLocked(uint32_t now) {
  return latest_jpeg_length > 0 && latest_frame_sequence > 0 &&
         now - latest_frame_captured_at <= CAMERA_FRAME_STALE_TIMEOUT_MS;
}

bool cameraFrameReady() {
  if (latest_frame_mutex == nullptr ||
      xSemaphoreTake(latest_frame_mutex,
                     pdMS_TO_TICKS(CAMERA_FRAME_LOCK_TIMEOUT_MS)) != pdTRUE) {
    return false;
  }

  const bool ready = latestFrameFreshLocked(millis());
  xSemaphoreGive(latest_frame_mutex);
  return ready;
}

bool copyLatestFrame(uint8_t **destination, size_t *destination_capacity,
                     size_t *jpeg_length, uint32_t *frame_sequence,
                     uint32_t last_frame_sequence, uint32_t timeout_ms) {
  if (destination == nullptr || destination_capacity == nullptr ||
      jpeg_length == nullptr || frame_sequence == nullptr ||
      latest_frame_mutex == nullptr) {
    return false;
  }

  const uint32_t started_at = millis();
  while (millis() - started_at < timeout_ms) {
    if (xSemaphoreTake(latest_frame_mutex,
                       pdMS_TO_TICKS(CAMERA_FRAME_LOCK_TIMEOUT_MS)) == pdTRUE) {
      const bool has_new_frame =
          latest_frame_sequence != last_frame_sequence &&
          latestFrameFreshLocked(millis());
      if (has_new_frame) {
        const bool copied = ensureBufferCapacity(
            destination, destination_capacity, latest_jpeg_length);
        if (!copied) {
          xSemaphoreGive(latest_frame_mutex);
          return false;
        }

        memcpy(*destination, latest_jpeg_buffer, latest_jpeg_length);
        *jpeg_length = latest_jpeg_length;
        *frame_sequence = latest_frame_sequence;
        xSemaphoreGive(latest_frame_mutex);
        return true;
      }

      xSemaphoreGive(latest_frame_mutex);
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }

  return false;
}

void cameraCaptureTask(void *) {
  uint32_t next_frame_at = millis();
  camera_capture_heartbeat_at = next_frame_at;
  Serial.printf("Camera capture task starting; settling for %u ms\n",
                static_cast<unsigned>(CAMERA_CAPTURE_STARTUP_DELAY_MS));
  vTaskDelay(pdMS_TO_TICKS(CAMERA_CAPTURE_STARTUP_DELAY_MS));

  while (true) {
    const int32_t wait_ms = static_cast<int32_t>(next_frame_at - millis());
    if (wait_ms > 0) {
      vTaskDelay(pdMS_TO_TICKS(wait_ms));
    }
    next_frame_at = millis() + CAMERA_FRAME_INTERVAL_MS;

    camera_capture_heartbeat_at = millis();
    camera_fb_t *frame = esp_camera_fb_get();
    camera_capture_heartbeat_at = millis();
    if (frame == nullptr) {
      ++camera_capture_failures;
      if (camera_capture_failures == 1 ||
          camera_capture_failures % 10 == 0) {
        Serial.printf("Camera frame capture failed; retrying (%lu)\n",
                      static_cast<unsigned long>(camera_capture_failures));
      }
      vTaskDelay(pdMS_TO_TICKS(CAMERA_CAPTURE_RETRY_DELAY_MS));
      continue;
    }

    uint8_t *jpeg_buffer = frame->buf;
    size_t jpeg_length = frame->len;
    bool allocated_jpeg = false;

    if (frame->format != PIXFORMAT_JPEG) {
      if (!frame2jpg(frame, 80, &jpeg_buffer, &jpeg_length)) {
        esp_camera_fb_return(frame);
        ++camera_capture_failures;
        vTaskDelay(pdMS_TO_TICKS(CAMERA_CAPTURE_RETRY_DELAY_MS));
        continue;
      }
      allocated_jpeg = true;
    }

    if (publishLatestFrame(jpeg_buffer, jpeg_length)) {
      camera_capture_failures = 0;
    } else {
      Serial.println("Camera frame copy failed; keeping previous frame");
    }

    if (allocated_jpeg) {
      free(jpeg_buffer);
    }
    esp_camera_fb_return(frame);
  }
}

void cameraCaptureSupervisorTask(void *) {
  while (true) {
    const uint32_t now = millis();
    const uint32_t capture_heartbeat_at = camera_capture_heartbeat_at;

    if ((capture_heartbeat_at != 0 &&
         now - capture_heartbeat_at > CAMERA_CAPTURE_WATCHDOG_TIMEOUT_MS)) {
      Serial.println("Camera capture stalled; restarting device");
      vTaskDelay(pdMS_TO_TICKS(100));
      ESP.restart();
    }

    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

bool startCameraCaptureTask() {
  latest_frame_mutex = xSemaphoreCreateMutex();
  if (latest_frame_mutex == nullptr) {
    Serial.println("Camera frame mutex creation failed");
    return false;
  }

  camera_capture_heartbeat_at = millis();
  if (xTaskCreate(cameraCaptureTask, "camera_capture",
                  CAMERA_CAPTURE_TASK_STACK_SIZE, nullptr,
                  CAMERA_CAPTURE_TASK_PRIORITY, nullptr) != pdPASS) {
    vSemaphoreDelete(latest_frame_mutex);
    latest_frame_mutex = nullptr;
    Serial.println("Camera capture task start failed");
    return false;
  }

  if (xTaskCreate(cameraCaptureSupervisorTask, "camera_watchdog",
                  CAMERA_CAPTURE_WATCHDOG_TASK_STACK_SIZE, nullptr,
                  CAMERA_CAPTURE_TASK_PRIORITY, nullptr) != pdPASS) {
    Serial.println("Camera capture watchdog start failed");
    return false;
  }

  return true;
}

bool writeClientBytes(WiFiClient &client, const uint8_t *data,
                      size_t length) {
  if (data == nullptr && length > 0) {
    return false;
  }

  const int socket_fd = client.fd();
  if (socket_fd < 0) {
    return false;
  }

  const uint32_t started_at = millis();
  size_t written_total = 0;
  while (written_total < length && client.connected()) {
    if (millis() - started_at >= CAMERA_CLIENT_WRITE_TIMEOUT_MS) {
      return false;
    }

    fd_set write_set;
    FD_ZERO(&write_set);
    FD_SET(socket_fd, &write_set);
    timeval wait = {};
    wait.tv_usec = 200000;
    const int selected = select(socket_fd + 1, nullptr, &write_set, nullptr,
                                &wait);
    if (selected < 0) {
      return false;
    }
    if (selected == 0) {
      if (millis() - started_at >= CAMERA_CLIENT_WRITE_TIMEOUT_MS) {
        return false;
      }
      continue;
    }

    const size_t remaining = length - written_total;
    const size_t chunk_length = remaining > 8192 ? 8192 : remaining;
    const int written = send(socket_fd, data + written_total, chunk_length,
                             MSG_DONTWAIT);
    if (written > 0) {
      written_total += static_cast<size_t>(written);
      continue;
    }
    if (written < 0 &&
        (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
      continue;
    }
    return false;
  }

  return written_total == length;
}

bool writeClientText(WiFiClient &client, const char *text) {
  return text != nullptr &&
         writeClientBytes(client, reinterpret_cast<const uint8_t *>(text),
                          strlen(text));
}

bool sendHttpResponse(WiFiClient &client, const char *status,
                      const char *content_type, const uint8_t *body,
                      size_t body_length) {
  char header[320];
  const int header_length = snprintf(
      header, sizeof(header),
      "HTTP/1.1 %s\r\n"
      "Content-Type: %s\r\n"
      "Content-Length: %lu\r\n"
      "Cache-Control: no-store\r\n"
      "Connection: close\r\n"
      "Access-Control-Allow-Origin: *\r\n"
      "\r\n",
      status, content_type, static_cast<unsigned long>(body_length));
  if (header_length < 0 || header_length >= static_cast<int>(sizeof(header))) {
    return false;
  }

  return writeClientBytes(client, reinterpret_cast<const uint8_t *>(header),
                          static_cast<size_t>(header_length)) &&
         writeClientBytes(client, body, body_length);
}

bool sendCameraUnavailable(WiFiClient &client) {
  static const char body[] = "camera frame unavailable\n";
  return sendHttpResponse(
      client, "503 Service Unavailable", "text/plain; charset=utf-8",
      reinterpret_cast<const uint8_t *>(body), strlen(body));
}

bool readCameraRequest(WiFiClient &client, char *path, size_t path_capacity) {
  if (path == nullptr || path_capacity == 0) {
    return false;
  }

  char line[256];
  size_t line_length = 0;
  bool request_line_read = false;
  const uint32_t started_at = millis();

  while (millis() - started_at < CAMERA_CLIENT_REQUEST_TIMEOUT_MS) {
    if (!client.available()) {
      vTaskDelay(pdMS_TO_TICKS(1));
      continue;
    }

    const int value = client.read();
    if (value < 0) {
      continue;
    }

    if (value == '\n') {
      line[line_length] = '\0';
      if (!request_line_read) {
        if (strncmp(line, "GET ", 4) != 0) {
          return false;
        }

        const char *path_start = line + 4;
        const char *path_end = strchr(path_start, ' ');
        if (path_end == nullptr || path_end == path_start) {
          return false;
        }

        const size_t path_length =
            static_cast<size_t>(path_end - path_start);
        if (path_length >= path_capacity) {
          return false;
        }
        memcpy(path, path_start, path_length);
        path[path_length] = '\0';
        char *query_start = strchr(path, '?');
        if (query_start != nullptr) {
          *query_start = '\0';
        }
        request_line_read = true;
      } else if (line_length == 0) {
        return true;
      }
      line_length = 0;
      continue;
    }

    if (value != '\r') {
      if (line_length + 1 >= sizeof(line)) {
        return false;
      }
      line[line_length++] = static_cast<char>(value);
    }
  }

  return false;
}

bool buildHealthJson(char *body, size_t body_capacity) {
  const bool connected = WiFi.status() == WL_CONNECTED;
  const String ip = connected ? WiFi.localIP().toString() : "";
  const bool camera_ready = cameraFrameReady();
  const int length = snprintf(
      body, body_capacity,
      "{\"status\":\"ok\",\"camera_id\":\"%s\","
      "\"wifi_connected\":%s,\"ip\":\"%s\","
      "\"uptime_ms\":%lu,\"camera_max_fps\":%u,"
      "\"camera_frame_ready\":%s,"
      "\"camera_max_http_clients\":%u}",
      CAMERA_ID, connected ? "true" : "false", ip.c_str(),
      static_cast<unsigned long>(millis()),
      static_cast<unsigned>(CAMERA_MAX_FPS), camera_ready ? "true" : "false",
      static_cast<unsigned>(CAMERA_MAX_HTTP_CLIENTS));
  return length >= 0 && length < static_cast<int>(body_capacity);
}

bool handleCameraStream(WiFiClient &client) {
  static const char stream_headers[] =
      "HTTP/1.1 200 OK\r\n"
      "Content-Type: multipart/x-mixed-replace;boundary=frame\r\n"
      "Cache-Control: no-store\r\n"
      "Access-Control-Allow-Origin: *\r\n"
      "Connection: close\r\n"
      "\r\n";
  if (!writeClientText(client, stream_headers)) {
    return false;
  }

  char part_header[96];
  uint8_t *jpeg_buffer = nullptr;
  size_t jpeg_capacity = 0;
  size_t jpeg_length = 0;
  uint32_t last_frame_sequence = 0;

  while (client.connected()) {
    if (!copyLatestFrame(&jpeg_buffer, &jpeg_capacity, &jpeg_length,
                         &last_frame_sequence, last_frame_sequence,
                         CAMERA_FRAME_WAIT_TIMEOUT_MS)) {
      break;
    }

    const int header_length =
        snprintf(part_header, sizeof(part_header), STREAM_PART,
                 static_cast<unsigned>(jpeg_length));
    if (header_length < 0 ||
        header_length >= static_cast<int>(sizeof(part_header)) ||
        !writeClientText(client, STREAM_BOUNDARY) ||
        !writeClientBytes(client,
                          reinterpret_cast<const uint8_t *>(part_header),
                          static_cast<size_t>(header_length)) ||
        !writeClientBytes(client, jpeg_buffer, jpeg_length)) {
      break;
    }

    vTaskDelay(pdMS_TO_TICKS(1));
  }

  free(jpeg_buffer);
  return false;
}

bool handleCameraSnapshot(WiFiClient &client) {
  uint8_t *jpeg_buffer = nullptr;
  size_t jpeg_capacity = 0;
  size_t jpeg_length = 0;
  uint32_t frame_sequence = 0;
  if (!copyLatestFrame(&jpeg_buffer, &jpeg_capacity, &jpeg_length,
                       &frame_sequence, 0, CAMERA_FRAME_WAIT_TIMEOUT_MS)) {
    free(jpeg_buffer);
    sendCameraUnavailable(client);
    return false;
  }

  const bool sent = sendHttpResponse(client, "200 OK", "image/jpeg",
                                     jpeg_buffer, jpeg_length);
  free(jpeg_buffer);
  return sent;
}

bool reserveCameraClient() {
  if (camera_client_mutex == nullptr ||
      xSemaphoreTake(camera_client_mutex,
                     pdMS_TO_TICKS(CAMERA_FRAME_LOCK_TIMEOUT_MS)) != pdTRUE) {
    return false;
  }

  const bool reserved = active_camera_clients < CAMERA_MAX_HTTP_CLIENTS;
  if (reserved) {
    ++active_camera_clients;
  }
  xSemaphoreGive(camera_client_mutex);
  return reserved;
}

void releaseCameraClient() {
  if (camera_client_mutex == nullptr ||
      xSemaphoreTake(camera_client_mutex,
                     pdMS_TO_TICKS(CAMERA_FRAME_LOCK_TIMEOUT_MS)) != pdTRUE) {
    return;
  }

  if (active_camera_clients > 0) {
    --active_camera_clients;
  }
  xSemaphoreGive(camera_client_mutex);
}

struct CameraClientContext {
  WiFiClient client;
};

void cameraClientTask(void *parameter) {
  CameraClientContext *context =
      static_cast<CameraClientContext *>(parameter);
  WiFiClient &client = context->client;
  client.setNoDelay(true);
  client.setTimeout(2);

  char path[128];
  if (!readCameraRequest(client, path, sizeof(path))) {
    static const char body[] = "bad request\n";
    sendHttpResponse(client, "400 Bad Request", "text/plain; charset=utf-8",
                     reinterpret_cast<const uint8_t *>(body), strlen(body));
  } else if (strcmp(path, "/") == 0) {
    static const char body[] =
        "smart-home-camera\n"
        "GET /stream for MJPEG\n"
        "GET /snapshot for one JPEG\n"
        "GET /health for status\n";
    sendHttpResponse(client, "200 OK", "text/plain; charset=utf-8",
                     reinterpret_cast<const uint8_t *>(body), strlen(body));
  } else if (strcmp(path, "/health") == 0) {
    char body[512];
    if (buildHealthJson(body, sizeof(body))) {
      sendHttpResponse(client, "200 OK", "application/json",
                       reinterpret_cast<const uint8_t *>(body), strlen(body));
    }
  } else if (strcmp(path, "/snapshot") == 0) {
    handleCameraSnapshot(client);
  } else if (strcmp(path, "/stream") == 0) {
    handleCameraStream(client);
  } else {
    static const char body[] = "not found\n";
    sendHttpResponse(client, "404 Not Found", "text/plain; charset=utf-8",
                     reinterpret_cast<const uint8_t *>(body), strlen(body));
  }

  client.stop();
  delete context;
  releaseCameraClient();
  vTaskDelete(nullptr);
}

void cameraHttpServerTask(void *) {
  Serial.printf("Camera HTTP server listening on port %u (max clients=%u)\n",
                static_cast<unsigned>(CAMERA_HTTP_PORT),
                static_cast<unsigned>(CAMERA_MAX_HTTP_CLIENTS));

  while (true) {
    WiFiClient client = camera_http_server.accept();
    if (!client) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }

    client.setNoDelay(true);
    if (!reserveCameraClient()) {
      static const char body[] = "camera busy\n";
      sendHttpResponse(client, "503 Service Unavailable",
                       "text/plain; charset=utf-8",
                       reinterpret_cast<const uint8_t *>(body), strlen(body));
      client.stop();
      continue;
    }

    CameraClientContext *context =
        new (std::nothrow) CameraClientContext{client};
    if (context == nullptr ||
        xTaskCreate(cameraClientTask, "camera_client",
                    CAMERA_CLIENT_TASK_STACK_SIZE, context,
                    CAMERA_CLIENT_TASK_PRIORITY, nullptr) != pdPASS) {
      if (context != nullptr) {
        context->client.stop();
        delete context;
      } else {
        client.stop();
      }
      releaseCameraClient();
    }
  }
}

bool startCameraHttpServer() {
  camera_client_mutex = xSemaphoreCreateMutex();
  if (camera_client_mutex == nullptr) {
    Serial.println("Camera HTTP client mutex creation failed");
    return false;
  }

  camera_http_server.begin();
  camera_http_server.setNoDelay(true);
  if (!camera_http_server) {
    camera_http_server.stop();
    vSemaphoreDelete(camera_client_mutex);
    camera_client_mutex = nullptr;
    Serial.println("Camera HTTP server start failed");
    return false;
  }

  if (xTaskCreate(cameraHttpServerTask, "camera_http",
                  CAMERA_HTTP_TASK_STACK_SIZE, nullptr,
                  CAMERA_HTTP_TASK_PRIORITY, nullptr) != pdPASS) {
    camera_http_server.stop();
    vSemaphoreDelete(camera_client_mutex);
    camera_client_mutex = nullptr;
    Serial.println("Camera HTTP server task start failed");
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

  if (!initCamera()) {
    Serial.println("Fatal initialization error; restarting in 5 seconds");
    delay(5000);
    ESP.restart();
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setHostname(CAMERA_ID);
  beginWifiConnection();

  if (!startCameraHttpServer()) {
    Serial.println("Fatal HTTP server error; restarting in 5 seconds");
    delay(5000);
    ESP.restart();
  }

  if (!startCameraCaptureTask()) {
    Serial.println("Fatal camera capture error; restarting in 5 seconds");
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
