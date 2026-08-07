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

// ApplianceSwitchState は appliance に紐づく1つの switchCode の現在状態。
// value が確定できない場合は nil (unknown) になる。
type ApplianceSwitchState struct {
	SwitchCode string `json:"switchCode"`
	Online     bool   `json:"online"`
	Value      *bool  `json:"value"`
	Source     string `json:"source"`
	Error      string `json:"error,omitempty"`
}

// ApplianceState は device の現在状態。value が確定できない場合は nil (unknown)。
// Source は "tuya" / "dry-run" / "no-action" など状態取得の根拠を返す。
// States には switchCode ごとの状態を保持し、既存クライアント向けに
// 1件だけの場合は従来のトップレベルフィールドにも同じ値を設定する。
type ApplianceState struct {
	ApplianceID string                 `json:"applianceId"`
	Online      bool                   `json:"online"`
	Value       *bool                  `json:"value"`
	SwitchCode  string                 `json:"switchCode"`
	Source      string                 `json:"source"`
	Error       string                 `json:"error,omitempty"`
	FetchedAt   string                 `json:"fetchedAt"`
	States      []ApplianceSwitchState `json:"states,omitempty"`
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

// GetApplianceState は appliance に紐づく Action から device ID / switch code を解決し、
// switchCode ごとに provider (Tuya) へ問い合わせて状態を返す。
// 1つも Action が無い、または deviceId を解決できない場合は value=nil, source="no-action" を返す。
// dry-run モードでは各 switchCode を source="dry-run" として返す。
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
	type stateTarget struct {
		deviceID   string
		switchCode string
		provider   domain.ProviderType
	}
	targets := make([]stateTarget, 0, len(actions))
	seenTargets := make(map[string]struct{}, len(actions))
	var lastErr error
	for _, a := range actions {
		deviceID, switchCode, err := s.executor.ResolveDevice(a)
		if err != nil {
			lastErr = err
			continue
		}
		target := stateTarget{deviceID: deviceID, switchCode: switchCode, provider: a.ProviderType}
		targetKey := string(target.provider) + "\x00" + target.deviceID + "\x00" + target.switchCode
		if _, seen := seenTargets[targetKey]; seen {
			continue
		}
		seenTargets[targetKey] = struct{}{}
		targets = append(targets, target)
	}
	if len(targets) == 0 {
		if lastErr != nil {
			state.Error = lastErr.Error()
			return state, lastErr
		}
		state.Source = "no-action"
		return state, nil
	}

	for _, target := range targets {
		ds, err := s.executor.GetDeviceState(ctx, target.deviceID, target.switchCode, target.provider)
		if err == nil {
			state.States = append(state.States, ApplianceSwitchState{
				SwitchCode: ds.SwitchCode,
				Online:     ds.Online,
				Value:      ds.Value,
				Source:     "tuya",
			})
			continue
		}
		// dry-run は致命ではないので、対象ごとに「不明」として返して次を試す。
		if errors.Is(err, executor.ErrDryRun) {
			state.States = append(state.States, ApplianceSwitchState{
				SwitchCode: target.switchCode,
				Source:     "dry-run",
			})
			continue
		}
		lastErr = err
		state.States = append(state.States, ApplianceSwitchState{
			SwitchCode: target.switchCode,
			Source:     "error",
			Error:      err.Error(),
		})
	}

	if len(state.States) == 1 {
		state.Online = state.States[0].Online
		state.SwitchCode = state.States[0].SwitchCode
		state.Value = state.States[0].Value
		state.Source = state.States[0].Source
		state.Error = state.States[0].Error
	} else {
		state.Source = summarizeStateSources(state.States)
	}
	if lastErr != nil {
		state.Error = lastErr.Error()
	}
	if len(state.States) > 0 && allStatesFailed(state.States) && lastErr != nil {
		return state, lastErr
	}
	return state, nil
}

func summarizeStateSources(states []ApplianceSwitchState) string {
	if len(states) == 0 {
		return "no-action"
	}
	source := states[0].Source
	for _, item := range states[1:] {
		if item.Source != source {
			return "mixed"
		}
	}
	return source
}

func allStatesFailed(states []ApplianceSwitchState) bool {
	for _, state := range states {
		if state.Source != "error" {
			return false
		}
	}
	return len(states) > 0
}
