package service

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/executor"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/store"
)

type fakeIRProvider struct {
	status     executor.IRLearnStatus
	statusErr  error
	executeErr error
	stopCalls  int
	executed   []domain.Action
}

func (f *fakeIRProvider) Validate(domain.Action) error { return nil }
func (f *fakeIRProvider) Execute(_ context.Context, action domain.Action) error {
	f.executed = append(f.executed, action)
	return f.executeErr
}
func (f *fakeIRProvider) ControllerID() string           { return "main-ir" }
func (f *fakeIRProvider) Configured() bool               { return true }
func (f *fakeIRProvider) LearningTimeout() time.Duration { return 30 * time.Second }
func (f *fakeIRProvider) Health(context.Context) (executor.IRHealth, error) {
	return executor.IRHealth{OK: true, State: "idle", WiFiConnected: true}, nil
}
func (f *fakeIRProvider) StartLearning(context.Context, time.Duration) (executor.IRLearnStatus, error) {
	return executor.IRLearnStatus{OK: true, State: "learning"}, nil
}
func (f *fakeIRProvider) LearningStatus(context.Context) (executor.IRLearnStatus, error) {
	return f.status, f.statusErr
}
func (f *fakeIRProvider) StopLearning(context.Context) (executor.IRLearnStatus, error) {
	f.stopCalls++
	return executor.IRLearnStatus{OK: true, State: "idle"}, nil
}
func (f *fakeIRProvider) TestSignal(context.Context) error { return nil }

type noopExecutor struct{}

func (noopExecutor) Validate(domain.Action) error                 { return nil }
func (noopExecutor) Execute(context.Context, domain.Action) error { return nil }

func TestIRLearningCaptureCanBeConfirmedAsAction(t *testing.T) {
	repository := store.NewMemory(store.SeedData{Appliances: []domain.Appliance{{
		ID: "appliance-ir", Name: "リビング照明", Category: "照明",
		ControlProvider: domain.ProviderESP32IR, ControllerID: "main-ir",
	}}})
	provider := &fakeIRProvider{status: executor.IRLearnStatus{
		OK: true, State: "captured",
		Capture: &executor.IRLearnCapture{
			CaptureID: "capture-1",
			Signal: executor.IRSignal{
				Protocol: "NEC", Bits: 32, Code: "0x00FF18E7", CarrierHz: 38000,
			},
		},
	}}
	appService := New(repository, executor.NewRegistry(noopExecutor{}, provider), 0, nil)

	session, err := appService.StartIRLearning(context.Background(), "appliance-ir", 30*time.Second)
	if err != nil {
		t.Fatalf("StartIRLearning() error = %v", err)
	}
	status, err := appService.IRLearningStatus(context.Background(), "appliance-ir")
	if err != nil {
		t.Fatalf("IRLearningStatus() error = %v", err)
	}
	if status.State != "captured" || status.Capture == nil || provider.stopCalls != 1 {
		t.Fatalf("status = %+v, stopCalls = %d", status, provider.stopCalls)
	}
	action, err := appService.ConfirmIRLearning(context.Background(), "appliance-ir", ConfirmIRLearningInput{
		SessionID: session.SessionID,
		CaptureID: "capture-1",
		Name:      "赤",
		Repeat:    2,
	})
	if err != nil {
		t.Fatalf("ConfirmIRLearning() error = %v", err)
	}
	if action.ProviderType != domain.ProviderESP32IR || action.Name != "赤" {
		t.Fatalf("action = %+v", action)
	}
	var params executor.IRParams
	if err := json.Unmarshal(action.Params, &params); err != nil {
		t.Fatalf("decode action params: %v", err)
	}
	if params.ControllerID != "main-ir" || params.Repeat != 2 || params.Signal.Code != "0x00FF18E7" {
		t.Fatalf("params = %+v", params)
	}
	if _, err := appService.IRLearningStatus(context.Background(), "appliance-ir"); err != ErrIRLearningNotFound {
		t.Fatalf("status after confirm error = %v, want ErrIRLearningNotFound", err)
	}
}

func TestIRLearningIsExclusiveAcrossAppliances(t *testing.T) {
	repository := store.NewMemory(store.SeedData{Appliances: []domain.Appliance{
		{ID: "ir-1", ControlProvider: domain.ProviderESP32IR, ControllerID: "main-ir"},
		{ID: "ir-2", ControlProvider: domain.ProviderESP32IR, ControllerID: "main-ir"},
	}})
	provider := &fakeIRProvider{}
	appService := New(repository, executor.NewRegistry(noopExecutor{}, provider), 0, nil)
	if _, err := appService.StartIRLearning(context.Background(), "ir-1", 30*time.Second); err != nil {
		t.Fatalf("first StartIRLearning() error = %v", err)
	}
	if _, err := appService.StartIRLearning(context.Background(), "ir-2", 30*time.Second); err != ErrIRLearningConflict {
		t.Fatalf("second StartIRLearning() error = %v, want ErrIRLearningConflict", err)
	}
}

func TestIRBusyManualExecutionReturnsConflictAfterLogging(t *testing.T) {
	repository := store.NewMemory(store.SeedData{
		Appliances: []domain.Appliance{{ID: "ir-1", ControlProvider: domain.ProviderESP32IR, ControllerID: "main-ir"}},
		Actions:    []domain.Action{{ID: "action-ir", ApplianceID: "ir-1", ProviderType: domain.ProviderESP32IR, Params: json.RawMessage(`{}`)}},
	})
	provider := &fakeIRProvider{executeErr: executor.ErrIRBusy}
	appService := New(repository, executor.NewRegistry(noopExecutor{}, provider), 0, nil)

	result, err := appService.ExecuteAction(context.Background(), "action-ir")
	if !errors.Is(err, executor.ErrIRBusy) || result.Success {
		t.Fatalf("ExecuteAction() = %+v, %v", result, err)
	}
	logs, listErr := repository.ListLogs(context.Background(), 10)
	if listErr != nil || len(logs) != 1 || logs[0].Status != domain.LogFailed {
		t.Fatalf("logs = %+v, error = %v", logs, listErr)
	}
}

func TestIRControllerTimeoutClearsLearningSession(t *testing.T) {
	repository := store.NewMemory(store.SeedData{Appliances: []domain.Appliance{{
		ID: "ir-1", ControlProvider: domain.ProviderESP32IR, ControllerID: "main-ir",
	}}})
	provider := &fakeIRProvider{statusErr: &executor.IRControllerError{StatusCode: 408, Code: "learn_timeout"}}
	appService := New(repository, executor.NewRegistry(noopExecutor{}, provider), 0, nil)
	if _, err := appService.StartIRLearning(context.Background(), "ir-1", 30*time.Second); err != nil {
		t.Fatalf("StartIRLearning() error = %v", err)
	}
	if _, err := appService.IRLearningStatus(context.Background(), "ir-1"); !errors.Is(err, ErrIRLearningTimeout) {
		t.Fatalf("IRLearningStatus() error = %v, want timeout", err)
	}
	if _, err := appService.IRLearningStatus(context.Background(), "ir-1"); !errors.Is(err, ErrIRLearningNotFound) {
		t.Fatalf("second IRLearningStatus() error = %v, want not found", err)
	}
}
