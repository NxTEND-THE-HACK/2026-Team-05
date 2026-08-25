package config

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var controllerIDPattern = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

type Config struct {
	Port           string
	AllowedOrigins []string
	DatabaseURL    string
	Cooldown       time.Duration
	Tuya           TuyaConfig
	IR             IRConfig
}

type TuyaConfig struct {
	AccessID  string
	SecretKey string
	Region    string
	Debug     bool
	DryRun    bool
	DeviceIDs map[string]string
}

type IRConfig struct {
	ControllerID    string
	BaseURL         string
	APIKey          string
	RequestTimeout  time.Duration
	LearningTimeout time.Duration
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
	irRequestTimeoutMS, err := intValue("IR_REQUEST_TIMEOUT_MS", 3000)
	if err != nil {
		return Config{}, err
	}
	if irRequestTimeoutMS < 100 || irRequestTimeoutMS > 30000 {
		return Config{}, errors.New("IR_REQUEST_TIMEOUT_MS must be between 100 and 30000")
	}
	irLearningTimeoutSeconds, err := intValue("IR_LEARNING_TIMEOUT_SECONDS", 30)
	if err != nil {
		return Config{}, err
	}
	if irLearningTimeoutSeconds < 5 || irLearningTimeoutSeconds > 120 {
		return Config{}, errors.New("IR_LEARNING_TIMEOUT_SECONDS must be between 5 and 120")
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
		IR: IRConfig{
			ControllerID:    value("IR_CONTROLLER_ID", "main-ir"),
			BaseURL:         strings.TrimRight(strings.TrimSpace(os.Getenv("IR_CONTROLLER_URL")), "/"),
			APIKey:          strings.TrimSpace(os.Getenv("IR_CONTROLLER_API_KEY")),
			RequestTimeout:  time.Duration(irRequestTimeoutMS) * time.Millisecond,
			LearningTimeout: time.Duration(irLearningTimeoutSeconds) * time.Second,
		},
	}

	if cfg.Port == "" {
		return Config{}, errors.New("PORT must not be empty")
	}
	if !cfg.Tuya.DryRun && (cfg.Tuya.AccessID == "" || cfg.Tuya.SecretKey == "") {
		return Config{}, errors.New("TUYA_ACCESS_ID and TUYA_SECRET_KEY are required unless TUYA_DRY_RUN=true")
	}
	if !controllerIDPattern.MatchString(cfg.IR.ControllerID) {
		return Config{}, errors.New("IR_CONTROLLER_ID may contain only letters, numbers, underscores, and hyphens")
	}
	if cfg.IR.BaseURL != "" {
		parsed, err := url.Parse(cfg.IR.BaseURL)
		if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" || parsed.User != nil {
			return Config{}, errors.New("IR_CONTROLLER_URL must be an absolute http or https URL without user information")
		}
		if cfg.IR.APIKey == "" {
			return Config{}, errors.New("IR_CONTROLLER_API_KEY is required when IR_CONTROLLER_URL is set")
		}
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
