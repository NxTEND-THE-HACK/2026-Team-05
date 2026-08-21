package config

import (
	"strings"
	"testing"
	"time"
)

func TestLoadDryRunDefaults(t *testing.T) {
	clearEnvironment(t)
	t.Setenv("TUYA_DRY_RUN", "true")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.Port != "8080" || cfg.Tuya.Region != "us" {
		t.Fatalf("unexpected defaults: %+v", cfg)
	}
	if cfg.Cooldown != 5*time.Second {
		t.Fatalf("Cooldown = %v, want 5s", cfg.Cooldown)
	}
	if cfg.IR.ControllerID != "main-ir" || cfg.IR.RequestTimeout != 3*time.Second || cfg.IR.LearningTimeout != 30*time.Second {
		t.Fatalf("unexpected IR defaults: %+v", cfg.IR)
	}
}

func TestLoadRequiresTuyaCredentialsOutsideDryRun(t *testing.T) {
	clearEnvironment(t)

	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "TUYA_ACCESS_ID") {
		t.Fatalf("Load() error = %v, want missing credentials", err)
	}
}

func TestLoadRejectsUnknownRegion(t *testing.T) {
	clearEnvironment(t)
	t.Setenv("TUYA_DRY_RUN", "true")
	t.Setenv("TUYA_REGION", "moon")

	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "TUYA_REGION") {
		t.Fatalf("Load() error = %v, want region error", err)
	}
}

func TestLoadIRControllerConfiguration(t *testing.T) {
	clearEnvironment(t)
	t.Setenv("TUYA_DRY_RUN", "true")
	t.Setenv("IR_CONTROLLER_ID", "living-room-ir")
	t.Setenv("IR_CONTROLLER_URL", "http://192.168.1.50/")
	t.Setenv("IR_CONTROLLER_API_KEY", "secret")
	t.Setenv("IR_REQUEST_TIMEOUT_MS", "1500")
	t.Setenv("IR_LEARNING_TIMEOUT_SECONDS", "45")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.IR.ControllerID != "living-room-ir" || cfg.IR.BaseURL != "http://192.168.1.50" {
		t.Fatalf("unexpected IR configuration: %+v", cfg.IR)
	}
	if cfg.IR.RequestTimeout != 1500*time.Millisecond || cfg.IR.LearningTimeout != 45*time.Second {
		t.Fatalf("unexpected IR timeouts: %+v", cfg.IR)
	}
}

func TestLoadRequiresIRAPIKeyWhenURLIsSet(t *testing.T) {
	clearEnvironment(t)
	t.Setenv("TUYA_DRY_RUN", "true")
	t.Setenv("IR_CONTROLLER_URL", "http://192.168.1.50")

	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "IR_CONTROLLER_API_KEY") {
		t.Fatalf("Load() error = %v, want missing API key error", err)
	}
}

func clearEnvironment(t *testing.T) {
	t.Helper()
	for _, key := range []string{
		"PORT", "ALLOWED_ORIGINS", "DATABASE_URL", "ACTION_COOLDOWN_SECONDS",
		"TUYA_ACCESS_ID", "TUYA_SECRET_KEY", "TUYA_REGION", "TUYA_DEBUG", "TUYA_DRY_RUN",
		"PLUG_A_ID", "PLUG_B_ID", "PLUG_C_ID",
		"IR_CONTROLLER_ID", "IR_CONTROLLER_URL", "IR_CONTROLLER_API_KEY",
		"IR_REQUEST_TIMEOUT_MS", "IR_LEARNING_TIMEOUT_SECONDS",
	} {
		t.Setenv(key, "")
	}
}
