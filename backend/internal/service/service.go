package service

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/executor"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/store"
)

var ErrInvalidAction = errors.New("invalid action")

type Service struct {
	store    store.Store
	executor *executor.Registry
	cooldown time.Duration
	now      func() time.Time
}

type DetectionResult struct {
	Status string            `json:"status"`
	Log    *domain.ActionLog `json:"log,omitempty"`
}

type ExecuteResult struct {
	Success bool   `json:"success"`
	Message string `json:"message,omitempty"`
}

// ApplianceState は device の現在状態。value が確定できない場合は nil (unknown)。
// Source は "tuya" / "dry-run" / "no-action" など状態取得の根拠を返す。
type ApplianceState struct {
	ApplianceID string `json:"applianceId"`
	Online      bool   `json:"online"`
	Value       *bool  `json:"value"`
	SwitchCode  string `json:"switchCode"`
	Source      string `json:"source"`
	Error       string `json:"error,omitempty"`
	FetchedAt   string `json:"fetchedAt"`
}

func New(repository store.Store, registry *executor.Registry, cooldown time.Duration) *Service {
	return &Service{store: repository, executor: registry, cooldown: cooldown, now: func() time.Time { return time.Now().UTC() }}
}

func (s *Service) ProcessDetection(ctx context.Context, event domain.DetectionEvent) (DetectionResult, error) {
	claim, err := s.store.ClaimDetection(ctx, event, s.cooldown, s.now())
	if err != nil {
		return DetectionResult{}, fmt.Errorf("claim detection: %w", err)
	}
	if claim.Duplicate {
		return DetectionResult{Status: "duplicate"}, nil
	}
	if claim.Action == nil {
		status := "rejected"
		if claim.Log != nil && claim.Log.Status == domain.LogCoolingDown {
			status = "cooling_down"
		}
		return DetectionResult{Status: status, Log: claim.Log}, nil
	}

	log := *claim.Log
	if err := s.executor.Execute(ctx, *claim.Action); err != nil {
		log.Status = domain.LogFailed
		log.ErrorMessage = err.Error()
	} else {
		log.Status = domain.LogSuccess
	}
	stored, err := s.store.AppendLog(ctx, log)
	if err != nil {
		return DetectionResult{}, fmt.Errorf("record action result: %w", err)
	}
	status := "executed"
	if stored.Status == domain.LogFailed {
		status = "failed"
	}
	return DetectionResult{Status: status, Log: &stored}, nil
}

func (s *Service) ExecuteAction(ctx context.Context, actionID string) (ExecuteResult, error) {
	action, err := s.store.ActionByID(ctx, actionID)
	if err != nil {
		return ExecuteResult{}, err
	}
	eventID, err := domain.NewID("manual")
	if err != nil {
		return ExecuteResult{}, err
	}
	now := s.now()
	log := domain.ActionLog{EventID: eventID, CameraID: "manual", MotionCode: "MANUAL_TRIGGER", ActionID: action.ID, ActionName: action.Name, DetectedAt: now}
	result := ExecuteResult{Success: true}
	if err := s.executor.Execute(ctx, action); err != nil {
		log.Status = domain.LogFailed
		log.ErrorMessage = err.Error()
		result.Success = false
		result.Message = err.Error()
	} else {
		log.Status = domain.LogSuccess
	}
	if _, err := s.store.AppendLog(ctx, log); err != nil {
		return ExecuteResult{}, fmt.Errorf("record manual action: %w", err)
	}
	return result, nil
}

func (s *Service) CreateAction(ctx context.Context, input domain.CreateActionInput) (domain.Action, error) {
	action := domain.Action{ApplianceID: input.ApplianceID, Name: input.Name, ProviderType: input.ProviderType, Params: input.Params}
	if err := s.executor.Validate(action); err != nil {
		return domain.Action{}, fmt.Errorf("%w: %v", ErrInvalidAction, err)
	}
	return s.store.CreateAction(ctx, input)
}

// GetApplianceState は appliance に紐づく Action のうち device ID を解決できるものを
// 1つ選んで provider (Tuya) へ問い合わせ、ON/OFF 状態を返す。
// 1つも Action が無い、または deviceId を解決できない場合は value=nil, source="no-action" を返す。
// dry-run モードでは ErrDryRun を検知して source="dry-run" を返す。
func (s *Service) GetApplianceState(ctx context.Context, applianceID string) (ApplianceState, error) {
	now := s.now().UTC().Format(time.RFC3339)
	state := ApplianceState{ApplianceID: applianceID, FetchedAt: now}
	actions, err := s.store.ListActions(ctx, applianceID)
	if err != nil {
		return state, fmt.Errorf("list actions: %w", err)
	}
	if len(actions) == 0 {
		state.Source = "no-action"
		return state, nil
	}
	var resolved *executor.DeviceState
	var lastErr error
	for _, a := range actions {
		deviceID, switchCode, err := s.executor.ResolveDevice(a)
		if err != nil {
			lastErr = err
			continue
		}
		ds, err := s.executor.GetDeviceState(ctx, deviceID, switchCode, a.ProviderType)
		if err == nil {
			resolved = &ds
			break
		}
		// dry-run は致命ではないので特別な source を立てて次を試す。
		if errors.Is(err, executor.ErrDryRun) {
			state.Source = "dry-run"
			return state, nil
		}
		lastErr = err
	}
	if resolved == nil {
		if lastErr != nil {
			return state, lastErr
		}
		state.Source = "no-action"
		return state, nil
	}
	state.Online = resolved.Online
	state.SwitchCode = resolved.SwitchCode
	state.Value = resolved.Value
	state.Source = "tuya"
	return state, nil
}
