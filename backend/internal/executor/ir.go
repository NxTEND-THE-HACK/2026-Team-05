package executor

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/config"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

const maxIRResponseBytes = 1 << 20

var (
	ErrIRNotConfigured = errors.New("infrared controller is not configured")
	ErrIRBusy          = errors.New("infrared controller is busy learning")
	ErrIRUnavailable   = errors.New("infrared controller is unavailable")

	irProtocolPattern = regexp.MustCompile(`^[A-Za-z0-9_+-]+$`)
	irHexPattern      = regexp.MustCompile(`^0x[0-9A-Fa-f]+$`)
)

type IRSignal struct {
	Protocol  string   `json:"protocol"`
	Bits      int      `json:"bits,omitempty"`
	Code      string   `json:"code,omitempty"`
	Address   string   `json:"address,omitempty"`
	Command   string   `json:"command,omitempty"`
	Raw       []uint32 `json:"raw,omitempty"`
	CarrierHz uint32   `json:"carrierHz"`
}

type IRParams struct {
	ControllerID string   `json:"controllerId"`
	Signal       IRSignal `json:"signal"`
	Repeat       int      `json:"repeat"`
}

type IRHealth struct {
	OK              bool   `json:"ok"`
	ControllerID    string `json:"controllerId,omitempty"`
	State           string `json:"state"`
	WiFiConnected   bool   `json:"wifiConnected"`
	RSSI            int    `json:"rssi,omitempty"`
	IP              string `json:"ip,omitempty"`
	FirmwareVersion string `json:"firmwareVersion,omitempty"`
	Message         string `json:"message,omitempty"`
}

type IRLearnCapture struct {
	CaptureID string   `json:"captureId"`
	IsRepeat  bool     `json:"isRepeat"`
	Signal    IRSignal `json:"signal"`
}

type IRLearnStatus struct {
	OK        bool            `json:"ok"`
	State     string          `json:"state"`
	Capture   *IRLearnCapture `json:"capture,omitempty"`
	ExpiresAt string          `json:"expiresAt,omitempty"`
	Error     string          `json:"error,omitempty"`
	Message   string          `json:"message,omitempty"`
}

type IRProvider interface {
	ActionExecutor
	ControllerID() string
	Configured() bool
	LearningTimeout() time.Duration
	Health(context.Context) (IRHealth, error)
	StartLearning(context.Context, time.Duration) (IRLearnStatus, error)
	LearningStatus(context.Context) (IRLearnStatus, error)
	StopLearning(context.Context) (IRLearnStatus, error)
	TestSignal(context.Context) error
}

type IRControllerError struct {
	StatusCode int
	Code       string
	Message    string
}

func (e *IRControllerError) Error() string {
	if e.Code != "" && e.Message != "" {
		return fmt.Sprintf("infrared controller returned %d (%s): %s", e.StatusCode, e.Code, e.Message)
	}
	if e.Message != "" {
		return fmt.Sprintf("infrared controller returned %d: %s", e.StatusCode, e.Message)
	}
	return fmt.Sprintf("infrared controller returned HTTP %d", e.StatusCode)
}

type IR struct {
	controllerID    string
	baseURL         string
	apiKey          string
	client          *http.Client
	logger          *slog.Logger
	learningTimeout time.Duration

	operationMu   sync.Mutex
	learning      bool
	learningUntil time.Time
	now           func() time.Time
}

func NewIR(cfg config.IRConfig, logger *slog.Logger) *IR {
	return &IR{
		controllerID:    cfg.ControllerID,
		baseURL:         strings.TrimRight(cfg.BaseURL, "/"),
		apiKey:          cfg.APIKey,
		client:          &http.Client{Timeout: cfg.RequestTimeout},
		logger:          logger,
		learningTimeout: cfg.LearningTimeout,
		now:             func() time.Time { return time.Now().UTC() },
	}
}

func (i *IR) ControllerID() string { return i.controllerID }

func (i *IR) Configured() bool { return i.baseURL != "" && i.apiKey != "" }

func (i *IR) LearningTimeout() time.Duration {
	if i.learningTimeout == 0 {
		return 30 * time.Second
	}
	return i.learningTimeout
}

func (i *IR) Validate(action domain.Action) error {
	_, err := i.params(action)
	return err
}

func (i *IR) Execute(ctx context.Context, action domain.Action) error {
	params, err := i.params(action)
	if err != nil {
		return err
	}
	if err := i.requireConfigured(); err != nil {
		return err
	}

	i.operationMu.Lock()
	defer i.operationMu.Unlock()
	if i.learningActiveLocked() {
		return ErrIRBusy
	}
	payload := struct {
		Signal IRSignal `json:"signal"`
		Repeat int      `json:"repeat"`
	}{Signal: params.Signal, Repeat: params.Repeat}
	var response struct {
		OK      bool   `json:"ok"`
		Message string `json:"message"`
	}
	if err := i.doJSON(ctx, http.MethodPost, "/api/send/signal", payload, &response); err != nil {
		return translateIRBusy(err)
	}
	if !response.OK {
		return fmt.Errorf("%w: signal transmission was not confirmed: %s", ErrIRUnavailable, response.Message)
	}
	i.logger.Info("infrared signal sent", "action_id", action.ID, "controller_id", params.ControllerID, "repeat", params.Repeat)
	return nil
}

func (i *IR) Health(ctx context.Context) (IRHealth, error) {
	if err := i.requireConfigured(); err != nil {
		return IRHealth{}, err
	}
	var response IRHealth
	if err := i.doJSON(ctx, http.MethodGet, "/api/health", nil, &response); err != nil {
		return IRHealth{}, err
	}
	response.ControllerID = i.controllerID
	return response, nil
}

func (i *IR) StartLearning(ctx context.Context, timeout time.Duration) (IRLearnStatus, error) {
	if err := i.requireConfigured(); err != nil {
		return IRLearnStatus{}, err
	}
	if timeout < 5*time.Second || timeout > 120*time.Second {
		return IRLearnStatus{}, fmt.Errorf("infrared learning timeout must be between 5 and 120 seconds")
	}

	i.operationMu.Lock()
	defer i.operationMu.Unlock()
	if i.learningActiveLocked() {
		return IRLearnStatus{}, ErrIRBusy
	}
	payload := struct {
		Mode           string `json:"mode"`
		TimeoutSeconds int    `json:"timeoutSeconds"`
	}{Mode: "single", TimeoutSeconds: int(timeout / time.Second)}
	var response IRLearnStatus
	if err := i.doJSON(ctx, http.MethodPost, "/api/learn/start", payload, &response); err != nil {
		return IRLearnStatus{}, translateIRBusy(err)
	}
	if !response.OK || response.State != "learning" {
		return IRLearnStatus{}, fmt.Errorf("%w: controller did not enter learning mode: state=%s message=%s", ErrIRUnavailable, response.State, response.Message)
	}
	i.learning = true
	i.learningUntil = i.now().Add(timeout)
	return response, nil
}

func (i *IR) LearningStatus(ctx context.Context) (IRLearnStatus, error) {
	if err := i.requireConfigured(); err != nil {
		return IRLearnStatus{}, err
	}
	i.operationMu.Lock()
	defer i.operationMu.Unlock()
	var response IRLearnStatus
	if err := i.doJSON(ctx, http.MethodGet, "/api/learn/status", nil, &response); err != nil {
		return IRLearnStatus{}, err
	}
	if response.State != "learning" {
		i.learning = false
		i.learningUntil = time.Time{}
	}
	return response, nil
}

func (i *IR) StopLearning(ctx context.Context) (IRLearnStatus, error) {
	if err := i.requireConfigured(); err != nil {
		return IRLearnStatus{}, err
	}
	i.operationMu.Lock()
	defer i.operationMu.Unlock()
	var response IRLearnStatus
	err := i.doJSON(ctx, http.MethodPost, "/api/learn/stop", struct{}{}, &response)
	i.learning = false
	i.learningUntil = time.Time{}
	return response, err
}

func (i *IR) TestSignal(ctx context.Context) error {
	if err := i.requireConfigured(); err != nil {
		return err
	}
	i.operationMu.Lock()
	defer i.operationMu.Unlock()
	if i.learningActiveLocked() {
		return ErrIRBusy
	}
	var response struct {
		OK      bool   `json:"ok"`
		Message string `json:"message"`
	}
	if err := i.doJSON(ctx, http.MethodPost, "/api/test/ir", struct{}{}, &response); err != nil {
		return translateIRBusy(err)
	}
	if !response.OK {
		return fmt.Errorf("%w: test signal was not confirmed: %s", ErrIRUnavailable, response.Message)
	}
	return nil
}

func (i *IR) params(action domain.Action) (IRParams, error) {
	var params IRParams
	decoder := json.NewDecoder(bytes.NewReader(action.Params))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&params); err != nil {
		return IRParams{}, fmt.Errorf("decode ESP32_IR params: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return IRParams{}, fmt.Errorf("ESP32_IR params must contain one JSON object")
	}
	params.ControllerID = strings.TrimSpace(params.ControllerID)
	if params.ControllerID == "" {
		return IRParams{}, fmt.Errorf("ESP32_IR params.controllerId is required")
	}
	if params.ControllerID != i.controllerID {
		return IRParams{}, fmt.Errorf("unknown infrared controller: %s", params.ControllerID)
	}
	if params.Repeat < 1 || params.Repeat > 5 {
		return IRParams{}, fmt.Errorf("ESP32_IR params.repeat must be between 1 and 5")
	}
	if err := ValidateIRSignal(params.Signal); err != nil {
		return IRParams{}, err
	}
	return params, nil
}

func ValidateIRSignal(signal IRSignal) error {
	protocol := strings.TrimSpace(signal.Protocol)
	if protocol == "" || len(protocol) > 32 || !irProtocolPattern.MatchString(protocol) {
		return fmt.Errorf("infrared signal protocol is required and contains invalid characters")
	}
	if signal.CarrierHz < 30000 || signal.CarrierHz > 60000 {
		return fmt.Errorf("infrared signal carrierHz must be between 30000 and 60000")
	}
	if signal.Code == "" && len(signal.Raw) == 0 {
		return fmt.Errorf("infrared signal requires code or raw timings")
	}
	if signal.Code != "" {
		if len(signal.Code) > 258 || !irHexPattern.MatchString(signal.Code) {
			return fmt.Errorf("infrared signal code must be a 0x-prefixed hexadecimal string")
		}
		if signal.Bits < 1 || signal.Bits > 1024 {
			return fmt.Errorf("infrared signal bits must be between 1 and 1024 when code is present")
		}
	}
	for name, value := range map[string]string{"address": signal.Address, "command": signal.Command} {
		if value != "" && (len(value) > 258 || !irHexPattern.MatchString(value)) {
			return fmt.Errorf("infrared signal %s must be a 0x-prefixed hexadecimal string", name)
		}
	}
	if len(signal.Raw) > 4096 {
		return fmt.Errorf("infrared signal raw timings must contain at most 4096 values")
	}
	for _, timing := range signal.Raw {
		if timing == 0 || timing > 1000000 {
			return fmt.Errorf("infrared signal raw timings must be between 1 and 1000000 microseconds")
		}
	}
	return nil
}

func (i *IR) requireConfigured() error {
	if !i.Configured() {
		return ErrIRNotConfigured
	}
	return nil
}

func (i *IR) learningActiveLocked() bool {
	if i.learning && !i.learningUntil.IsZero() && !i.now().Before(i.learningUntil) {
		i.learning = false
		i.learningUntil = time.Time{}
	}
	return i.learning
}

func (i *IR) doJSON(ctx context.Context, method, path string, input any, output any) error {
	var body io.Reader
	if input != nil {
		encoded, err := json.Marshal(input)
		if err != nil {
			return fmt.Errorf("encode infrared controller request: %w", err)
		}
		body = bytes.NewReader(encoded)
	}
	request, err := http.NewRequestWithContext(ctx, method, i.baseURL+path, body)
	if err != nil {
		return fmt.Errorf("create infrared controller request: %w", err)
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("X-API-Key", i.apiKey)
	if input != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	response, err := i.client.Do(request)
	if err != nil {
		return fmt.Errorf("%w: %w", ErrIRUnavailable, err)
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, maxIRResponseBytes+1))
	if err != nil {
		return fmt.Errorf("%w: read response: %v", ErrIRUnavailable, err)
	}
	if len(data) > maxIRResponseBytes {
		return fmt.Errorf("%w: response exceeds 1 MB", ErrIRUnavailable)
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		var failure struct {
			Error   string `json:"error"`
			Message string `json:"message"`
		}
		_ = json.Unmarshal(data, &failure)
		return &IRControllerError{StatusCode: response.StatusCode, Code: failure.Error, Message: failure.Message}
	}
	if output == nil || len(bytes.TrimSpace(data)) == 0 {
		return nil
	}
	if err := json.Unmarshal(data, output); err != nil {
		return fmt.Errorf("%w: decode response: %v", ErrIRUnavailable, err)
	}
	return nil
}

func translateIRBusy(err error) error {
	var controllerErr *IRControllerError
	if errors.As(err, &controllerErr) && controllerErr.StatusCode == http.StatusConflict {
		return fmt.Errorf("%w: %v", ErrIRBusy, err)
	}
	return err
}
