package api

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"testing"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/executor"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/service"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/store"
)

type apiFakeIRProvider struct {
	executeCalls int
	executeErr   error
}

func (f *apiFakeIRProvider) Validate(domain.Action) error { return nil }
func (f *apiFakeIRProvider) Execute(context.Context, domain.Action) error {
	f.executeCalls++
	return f.executeErr
}
func (f *apiFakeIRProvider) ControllerID() string           { return "main-ir" }
func (f *apiFakeIRProvider) Configured() bool               { return true }
func (f *apiFakeIRProvider) LearningTimeout() time.Duration { return 30 * time.Second }
func (f *apiFakeIRProvider) Health(context.Context) (executor.IRHealth, error) {
	return executor.IRHealth{OK: true, State: "idle", WiFiConnected: true}, nil
}
func (f *apiFakeIRProvider) StartLearning(context.Context, time.Duration) (executor.IRLearnStatus, error) {
	return executor.IRLearnStatus{OK: true, State: "learning"}, nil
}
func (f *apiFakeIRProvider) LearningStatus(context.Context) (executor.IRLearnStatus, error) {
	return executor.IRLearnStatus{
		OK: true, State: "captured",
		Capture: &executor.IRLearnCapture{
			CaptureID: "capture-api-1",
			Signal:    executor.IRSignal{Protocol: "NEC", Bits: 32, Code: "0x00FF18E7", CarrierHz: 38000},
		},
	}, nil
}
func (f *apiFakeIRProvider) StopLearning(context.Context) (executor.IRLearnStatus, error) {
	return executor.IRLearnStatus{OK: true, State: "idle"}, nil
}
func (f *apiFakeIRProvider) TestSignal(context.Context) error { return nil }

func TestIRLearningAPIRegistersAndExecutesAction(t *testing.T) {
	repository := store.NewMemory(store.DefaultSeed(time.Now()))
	irProvider := &apiFakeIRProvider{}
	registry := executor.NewRegistry(&recordingExecutor{}, irProvider)
	server := New(repository, service.New(repository, registry, 0, nil), slog.New(slog.NewTextHandler(io.Discard, nil)), []string{"*"}, nil)

	created := performRequest(server, http.MethodPost, "/api/appliances", `{"name":"リビング照明","category":"照明","controlProvider":"ESP32_IR"}`)
	if created.Code != http.StatusCreated {
		t.Fatalf("create appliance = %d %s", created.Code, created.Body.String())
	}
	var appliance domain.Appliance
	if err := json.Unmarshal(created.Body.Bytes(), &appliance); err != nil {
		t.Fatalf("decode appliance: %v", err)
	}
	if appliance.ControlProvider != domain.ProviderESP32IR || appliance.ControllerID != "main-ir" {
		t.Fatalf("appliance = %+v", appliance)
	}

	basePath := "/api/appliances/" + appliance.ID + "/ir"
	started := performRequest(server, http.MethodPost, basePath+"/learn/start", `{}`)
	if started.Code != http.StatusOK {
		t.Fatalf("start learning = %d %s", started.Code, started.Body.String())
	}
	var session service.IRLearningSession
	if err := json.Unmarshal(started.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode learning session: %v", err)
	}

	status := performRequest(server, http.MethodGet, basePath+"/learn/status", "")
	if status.Code != http.StatusOK || !json.Valid(status.Body.Bytes()) {
		t.Fatalf("learning status = %d %s", status.Code, status.Body.String())
	}
	confirmBody := fmt.Sprintf(`{"sessionId":%q,"captureId":"capture-api-1","name":"赤","repeat":1}`, session.SessionID)
	confirmed := performRequest(server, http.MethodPost, basePath+"/learn/confirm", confirmBody)
	if confirmed.Code != http.StatusCreated {
		t.Fatalf("confirm learning = %d %s", confirmed.Code, confirmed.Body.String())
	}
	var action domain.Action
	if err := json.Unmarshal(confirmed.Body.Bytes(), &action); err != nil {
		t.Fatalf("decode action: %v", err)
	}
	if action.Name != "赤" || action.ProviderType != domain.ProviderESP32IR {
		t.Fatalf("action = %+v", action)
	}

	executed := performRequest(server, http.MethodPost, "/api/actions/"+action.ID+"/execute", "")
	if executed.Code != http.StatusOK || irProvider.executeCalls != 1 {
		t.Fatalf("execute = %d %s, calls=%d", executed.Code, executed.Body.String(), irProvider.executeCalls)
	}
	irProvider.executeErr = executor.ErrIRBusy
	busy := performRequest(server, http.MethodPost, "/api/actions/"+action.ID+"/execute", "")
	if busy.Code != http.StatusConflict || irProvider.executeCalls != 2 {
		t.Fatalf("busy execute = %d %s, calls=%d", busy.Code, busy.Body.String(), irProvider.executeCalls)
	}
}
