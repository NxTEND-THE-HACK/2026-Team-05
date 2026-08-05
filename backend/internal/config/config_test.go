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

func clearEnvironment(t *testing.T) {
	t.Helper()
	for _, key := range []string{
		"PORT", "ALLOWED_ORIGINS", "DATABASE_URL", "ACTION_COOLDOWN_SECONDS",
		"TUYA_ACCESS_ID", "TUYA_SECRET_KEY", "TUYA_REGION", "TUYA_DEBUG", "TUYA_DRY_RUN",
		"PLUG_A_ID", "PLUG_B_ID", "PLUG_C_ID",
	} {
		t.Setenv(key, "")
	}
}
