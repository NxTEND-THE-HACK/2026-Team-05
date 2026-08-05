package executor

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"strings"
	"testing"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/config"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

func TestTuyaDryRunAllowsConfiguredEnvironmentSlot(t *testing.T) {
	client, err := NewTuya(config.TuyaConfig{
		Region:    "us",
		DryRun:    true,
		DeviceIDs: map[string]string{"PLUG_A_ID": ""},
	}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		t.Fatalf("NewTuya() error = %v", err)
	}
	action := domain.Action{ID: "action-1", ProviderType: domain.ProviderTuya, Params: json.RawMessage(`{"deviceIdEnv":"PLUG_A_ID","value":true}`)}
	if err := client.Validate(action); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
	if err := client.Execute(context.Background(), action); err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
}

func TestTuyaRejectsUnapprovedEnvironmentVariable(t *testing.T) {
	client, err := NewTuya(config.TuyaConfig{Region: "us", DryRun: true, DeviceIDs: map[string]string{}}, slog.Default())
	if err != nil {
		t.Fatalf("NewTuya() error = %v", err)
	}
	action := domain.Action{ProviderType: domain.ProviderTuya, Params: json.RawMessage(`{"deviceIdEnv":"HOME","value":true}`)}
	err = client.Validate(action)
	if err == nil || !strings.Contains(err.Error(), "not allowed") {
		t.Fatalf("Validate() error = %v, want allow-list error", err)
	}
}

func TestTuyaRequiresBooleanValue(t *testing.T) {
	client, err := NewTuya(config.TuyaConfig{Region: "jp", DryRun: true, DeviceIDs: map[string]string{}}, slog.Default())
	if err != nil {
		t.Fatalf("NewTuya() error = %v", err)
	}
	action := domain.Action{ProviderType: domain.ProviderTuya, Params: json.RawMessage(`{"deviceId":"device-1"}`)}
	err = client.Validate(action)
	if err == nil || !strings.Contains(err.Error(), "value is required") {
		t.Fatalf("Validate() error = %v, want value error", err)
	}
}

func TestTuyaRejectsUnknownParams(t *testing.T) {
	client, err := NewTuya(config.TuyaConfig{Region: "us", DryRun: true, DeviceIDs: map[string]string{}}, slog.Default())
	if err != nil {
		t.Fatalf("NewTuya() error = %v", err)
	}
	action := domain.Action{ProviderType: domain.ProviderTuya, Params: json.RawMessage(`{"deviceId":"device-1","value":true,"typo":true}`)}
	err = client.Validate(action)
	if err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("Validate() error = %v, want unknown field error", err)
	}
}
