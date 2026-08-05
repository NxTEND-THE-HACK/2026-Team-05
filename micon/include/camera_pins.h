#pragma once

// XIAO ESP32S3 Sense camera expansion board pin map.
// These are ESP32-S3 GPIO numbers, not the D0/D1/... silkscreen labels.
#define XCLK_GPIO_NUM 10
#define SIOD_GPIO_NUM 40
#define SIOC_GPIO_NUM 39

#define Y2_GPIO_NUM 15
#define Y3_GPIO_NUM 17
#define Y4_GPIO_NUM 18
#define Y5_GPIO_NUM 16
#define Y6_GPIO_NUM 14
#define Y7_GPIO_NUM 12
#define Y8_GPIO_NUM 11
#define Y9_GPIO_NUM 48

#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM 47
#define PCLK_GPIO_NUM 13

// The XIAO camera module does not expose separate power-down/reset pins.
#define PWDN_GPIO_NUM -1
#define RESET_GPIO_NUM -1

