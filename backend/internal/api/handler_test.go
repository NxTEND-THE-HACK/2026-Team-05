package api

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/executor"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/service"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/store"
)

type recordingExecutor struct {
	mu      sync.Mutex
	actions []domain.Action
}

func (e *recordingExecutor) Validate(domain.Action) error { return nil }
func (e *recordingExecutor) Execute(_ context.Context, action domain.Action) error {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.actions = append(e.actions, action)
	return nil
}

func TestDetectionEndpointExecutesBoundTuyaActionOnce(t *testing.T) {
	repository := store.NewMemory(store.DefaultSeed(time.Now()))
	if _, err := repository.CreateBinding(context.Background(), domain.CreateBindingInput{
		MotionID: "motion-pose-right-hand-up", ActionID: "action-plug-a-on",
	}); err != nil {
		t.Fatalf("CreateBinding() error = %v", err)
	}
	recorder := &recordingExecutor{}
	registry := executor.NewRegistry(recorder)
	appService := service.New(repository, registry, 5*time.Second)
	server := New(repository, appService, slog.New(slog.NewTextHandler(io.Discard, nil)), []string{"http://localhost:5173"})
	payload := `{"event_id":"event-http-1","camera_id":"demo-camera-1","motion_code":"POSE_RIGHT_HAND_UP","confidence":0.93,"detected_at":"2026-08-05T12:00:00Z"}`

	first := performRequest(server, http.MethodPost, "/internal/detections", payload)
	if first.Code != http.StatusOK {
		t.Fatalf("first status = %d, body = %s", first.Code, first.Body.String())
	}
	var firstBody struct {
		Status string `json:"status"`
	}
	if err := json.Unmarshal(first.Body.Bytes(), &firstBody); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if firstBody.Status != "executed" {
		t.Fatalf("status = %q, want executed", firstBody.Status)
	}

	second := performRequest(server, http.MethodPost, "/internal/detections", payload)
	if second.Code != http.StatusOK || !strings.Contains(second.Body.String(), `"status":"duplicate"`) {
		t.Fatalf("duplicate response = %d %s", second.Code, second.Body.String())
	}
	recorder.mu.Lock()
	defer recorder.mu.Unlock()
	if len(recorder.actions) != 1 || recorder.actions[0].ID != "action-plug-a-on" {
		t.Fatalf("executed actions = %+v", recorder.actions)
	}
}

func TestDetectionEndpointRejectsMotionWithoutBinding(t *testing.T) {
	repository := store.NewMemory(store.DefaultSeed(time.Now()))
	recorder := &recordingExecutor{}
	registry := executor.NewRegistry(recorder)
	server := New(repository, service.New(repository, registry, 5*time.Second), slog.New(slog.NewTextHandler(io.Discard, nil)), []string{"*"})
	payload := `{"event_id":"event-http-unbound","camera_id":"demo-camera-1","motion_code":"POSE_RIGHT_HAND_UP","confidence":0.93,"detected_at":"2026-08-05T12:00:00Z"}`

	response := performRequest(server, http.MethodPost, "/internal/detections", payload)
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"status":"rejected"`) {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
	recorder.mu.Lock()
	defer recorder.mu.Unlock()
	if len(recorder.actions) != 0 {
		t.Fatalf("executed actions = %+v, want none", recorder.actions)
	}
}

func TestDetectionEndpointRejectsUnknownFields(t *testing.T) {
	repository := store.NewMemory(store.DefaultSeed(time.Now()))
	registry := executor.NewRegistry(&recordingExecutor{})
	server := New(repository, service.New(repository, registry, 0), slog.New(slog.NewTextHandler(io.Discard, nil)), []string{"*"})
	payload := `{"event_id":"event-http-2","camera_id":"demo-camera-1","motion_code":"POSE_RIGHT_HAND_UP","confidence":0.93,"detected_at":"2026-08-05T12:00:00Z","unexpected":true}`

	response := performRequest(server, http.MethodPost, "/internal/detections", payload)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestFrontendListResponsesUseExpectedEnvelope(t *testing.T) {
	repository := store.NewMemory(store.DefaultSeed(time.Now()))
	registry := executor.NewRegistry(&recordingExecutor{})
	server := New(repository, service.New(repository, registry, 0), slog.New(slog.NewTextHandler(io.Discard, nil)), []string{"*"})

	for _, pathAndKey := range [][2]string{{"/api/cameras", "cameras"}, {"/api/motions", "motions"}, {"/api/appliances", "appliances"}, {"/api/actions", "actions"}, {"/api/bindings", "bindings"}, {"/api/logs", "logs"}} {
		response := performRequest(server, http.MethodGet, pathAndKey[0], "")
		if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"`+pathAndKey[1]+`":`) {
			t.Errorf("GET %s = %d %s", pathAndKey[0], response.Code, response.Body.String())
		}
	}
}

func performRequest(server http.Handler, method, path, body string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	if body != "" {
		request.Header.Set("Content-Type", "application/json")
	}
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)
	return response
}
