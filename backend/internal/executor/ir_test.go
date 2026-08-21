package executor

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/config"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

func TestIRExecuteSendsSignalWithAPIKey(t *testing.T) {
	var received struct {
		Signal IRSignal `json:"signal"`
		Repeat int      `json:"repeat"`
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/send/signal" || r.Method != http.MethodPost {
			t.Errorf("request = %s %s", r.Method, r.URL.Path)
		}
		if got := r.Header.Get("X-API-Key"); got != "test-key" {
			t.Errorf("X-API-Key = %q", got)
		}
		if err := json.NewDecoder(r.Body).Decode(&received); err != nil {
			t.Errorf("decode request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"ok":true}`)
	}))
	defer server.Close()

	client := newTestIR(server.URL)
	action := irTestAction(t, 3)
	if err := client.Validate(action); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
	if err := client.Execute(context.Background(), action); err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if received.Repeat != 3 || received.Signal.Code != "0x00FF18E7" || received.Signal.CarrierHz != 38000 {
		t.Fatalf("received payload = %+v", received)
	}
}

func TestIRLearningBlocksTransmissionUntilCapture(t *testing.T) {
	sendCalls := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/api/learn/start":
			_, _ = io.WriteString(w, `{"ok":true,"state":"learning"}`)
		case "/api/learn/status":
			_, _ = io.WriteString(w, `{"ok":true,"state":"captured","capture":{"captureId":"capture-1","isRepeat":false,"signal":{"protocol":"NEC","bits":32,"code":"0x00FF18E7","carrierHz":38000}}}`)
		case "/api/send/signal":
			sendCalls++
			_, _ = io.WriteString(w, `{"ok":true}`)
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	client := newTestIR(server.URL)
	if _, err := client.StartLearning(context.Background(), 30*time.Second); err != nil {
		t.Fatalf("StartLearning() error = %v", err)
	}
	if err := client.Execute(context.Background(), irTestAction(t, 1)); !errors.Is(err, ErrIRBusy) {
		t.Fatalf("Execute() error = %v, want ErrIRBusy", err)
	}
	if sendCalls != 0 {
		t.Fatalf("sendCalls = %d while learning", sendCalls)
	}
	status, err := client.LearningStatus(context.Background())
	if err != nil || status.Capture == nil || status.Capture.CaptureID != "capture-1" {
		t.Fatalf("LearningStatus() = %+v, %v", status, err)
	}
	if err := client.Execute(context.Background(), irTestAction(t, 1)); err != nil {
		t.Fatalf("Execute() after capture error = %v", err)
	}
	if sendCalls != 1 {
		t.Fatalf("sendCalls = %d, want 1", sendCalls)
	}
}

func TestIRRejectsUnsafeOrIncompleteSignals(t *testing.T) {
	client := newTestIR("http://127.0.0.1")
	params, _ := json.Marshal(IRParams{
		ControllerID: "main-ir",
		Repeat:       1,
		Signal:       IRSignal{Protocol: "NEC", Code: "1234", Bits: 32, CarrierHz: 38000},
	})
	err := client.Validate(domain.Action{ProviderType: domain.ProviderESP32IR, Params: params})
	if err == nil {
		t.Fatal("Validate() succeeded for a code without a 0x prefix")
	}

	params, _ = json.Marshal(IRParams{
		ControllerID: "main-ir",
		Repeat:       1,
		Signal:       IRSignal{Protocol: "UNKNOWN", CarrierHz: 38000},
	})
	err = client.Validate(domain.Action{ProviderType: domain.ProviderESP32IR, Params: params})
	if err == nil {
		t.Fatal("Validate() succeeded without code or raw timings")
	}
}

func newTestIR(baseURL string) *IR {
	return NewIR(config.IRConfig{
		ControllerID:    "main-ir",
		BaseURL:         baseURL,
		APIKey:          "test-key",
		RequestTimeout:  time.Second,
		LearningTimeout: 30 * time.Second,
	}, slog.New(slog.NewTextHandler(io.Discard, nil)))
}

func irTestAction(t *testing.T, repeat int) domain.Action {
	t.Helper()
	params, err := json.Marshal(IRParams{
		ControllerID: "main-ir",
		Repeat:       repeat,
		Signal: IRSignal{
			Protocol:  "NEC",
			Bits:      32,
			Code:      "0x00FF18E7",
			Address:   "0x00FF",
			Command:   "0x18",
			CarrierHz: 38000,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	return domain.Action{ID: "action-ir-red", ProviderType: domain.ProviderESP32IR, Params: params}
}
