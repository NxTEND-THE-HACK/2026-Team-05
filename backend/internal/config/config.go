package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Port           string
	AllowedOrigins []string
	DatabaseURL    string
	Cooldown       time.Duration
	Tuya           TuyaConfig
}

type TuyaConfig struct {
	AccessID  string
	SecretKey string
	Region    string
	Debug     bool
	DryRun    bool
	DeviceIDs map[string]string
}

func Load() (Config, error) {
	dryRun, err := boolValue("TUYA_DRY_RUN", false)
	if err != nil {
		return Config{}, err
	}
	debug, err := boolValue("TUYA_DEBUG", false)
	if err != nil {
		return Config{}, err
	}
	cooldownSeconds, err := intValue("ACTION_COOLDOWN_SECONDS", 5)
	if err != nil {
		return Config{}, err
	}
	if cooldownSeconds < 0 {
		return Config{}, errors.New("ACTION_COOLDOWN_SECONDS must not be negative")
	}

	region := strings.ToLower(value("TUYA_REGION", "us"))
	if !oneOf(region, "jp", "us", "eu", "cn", "in") {
		return Config{}, fmt.Errorf("TUYA_REGION must be one of jp, us, eu, cn, in: %q", region)
	}

	cfg := Config{
		Port:           value("PORT", "8080"),
		AllowedOrigins: csvValue("ALLOWED_ORIGINS", []string{"http://localhost:5173"}),
		DatabaseURL:    strings.TrimSpace(os.Getenv("DATABASE_URL")),
		Cooldown:       time.Duration(cooldownSeconds) * time.Second,
		Tuya: TuyaConfig{
			AccessID:  strings.TrimSpace(os.Getenv("TUYA_ACCESS_ID")),
			SecretKey: strings.TrimSpace(os.Getenv("TUYA_SECRET_KEY")),
			Region:    region,
			Debug:     debug,
			DryRun:    dryRun,
			DeviceIDs: map[string]string{
				"PLUG_A_ID": strings.TrimSpace(os.Getenv("PLUG_A_ID")),
				"PLUG_B_ID": strings.TrimSpace(os.Getenv("PLUG_B_ID")),
				"PLUG_C_ID": strings.TrimSpace(os.Getenv("PLUG_C_ID")),
			},
		},
	}

	if cfg.Port == "" {
		return Config{}, errors.New("PORT must not be empty")
	}
	if !cfg.Tuya.DryRun && (cfg.Tuya.AccessID == "" || cfg.Tuya.SecretKey == "") {
		return Config{}, errors.New("TUYA_ACCESS_ID and TUYA_SECRET_KEY are required unless TUYA_DRY_RUN=true")
	}
	return cfg, nil
}

func value(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func boolValue(key string, fallback bool) (bool, error) {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback, nil
	}
	v, err := strconv.ParseBool(raw)
	if err != nil {
		return false, fmt.Errorf("%s must be a boolean: %w", key, err)
	}
	return v, nil
}

func intValue(key string, fallback int) (int, error) {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback, nil
	}
	v, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer: %w", key, err)
	}
	return v, nil
}

func csvValue(key string, fallback []string) []string {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	parts := strings.Split(raw, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		if v := strings.TrimSpace(part); v != "" {
			result = append(result, v)
		}
	}
	return result
}

func oneOf(value string, candidates ...string) bool {
	for _, candidate := range candidates {
		if value == candidate {
			return true
		}
	}
	return false
}
