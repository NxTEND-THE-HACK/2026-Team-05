package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/executor"
)

type IRLearningSession struct {
	SessionID    string                   `json:"sessionId"`
	ApplianceID  string                   `json:"applianceId"`
	ControllerID string                   `json:"controllerId"`
	State        string                   `json:"state"`
	ExpiresAt    time.Time                `json:"expiresAt"`
	Capture      *executor.IRLearnCapture `json:"capture,omitempty"`
}

type ConfirmIRLearningInput struct {
	SessionID string `json:"sessionId"`
	CaptureID string `json:"captureId"`
	Name      string `json:"name"`
	Repeat    int    `json:"repeat"`
}

func (s *Service) DefaultIRControllerID() string {
	provider, err := s.executor.IRProvider()
	if err != nil {
		return "main-ir"
	}
	return provider.ControllerID()
}

func (s *Service) IRHealth(ctx context.Context, applianceID string) (executor.IRHealth, error) {
	appliance, err := s.store.ApplianceByID(ctx, applianceID)
	if err != nil {
		return executor.IRHealth{}, err
	}
	provider, err := s.irProviderForAppliance(appliance)
	if err != nil {
		return executor.IRHealth{}, err
	}
	return provider.Health(ctx)
}

func (s *Service) StartIRLearning(ctx context.Context, applianceID string, timeout time.Duration) (IRLearningSession, error) {
	appliance, err := s.store.ApplianceByID(ctx, applianceID)
	if err != nil {
		return IRLearningSession{}, err
	}
	provider, err := s.irProviderForAppliance(appliance)
	if err != nil {
		return IRLearningSession{}, err
	}
	if timeout == 0 {
		timeout = provider.LearningTimeout()
	}
	if timeout < 5*time.Second || timeout > 120*time.Second {
		return IRLearningSession{}, fmt.Errorf("%w: timeoutSeconds must be between 5 and 120", ErrInvalidAction)
	}

	s.irMu.Lock()
	defer s.irMu.Unlock()
	if active := s.activeSessionLocked(); active != nil {
		if s.now().Before(active.ExpiresAt) {
			return IRLearningSession{}, ErrIRLearningConflict
		}
		_, _ = provider.StopLearning(ctx)
		delete(s.irSessions, active.SessionID)
		s.activeIRSessionID = ""
	}
	if _, err := provider.StartLearning(ctx, timeout); err != nil {
		return IRLearningSession{}, err
	}
	sessionID, err := domain.NewID("ir-learn")
	if err != nil {
		_, _ = provider.StopLearning(ctx)
		return IRLearningSession{}, err
	}
	session := &IRLearningSession{
		SessionID:    sessionID,
		ApplianceID:  appliance.ID,
		ControllerID: provider.ControllerID(),
		State:        "learning",
		ExpiresAt:    s.now().Add(timeout),
	}
	s.irSessions[sessionID] = session
	s.activeIRSessionID = sessionID
	return *session, nil
}

func (s *Service) IRLearningStatus(ctx context.Context, applianceID string) (IRLearningSession, error) {
	appliance, err := s.store.ApplianceByID(ctx, applianceID)
	if err != nil {
		return IRLearningSession{}, err
	}
	provider, err := s.irProviderForAppliance(appliance)
	if err != nil {
		return IRLearningSession{}, err
	}

	s.irMu.Lock()
	defer s.irMu.Unlock()
	session := s.activeSessionLocked()
	if session == nil || session.ApplianceID != applianceID {
		return IRLearningSession{}, ErrIRLearningNotFound
	}
	if !s.now().Before(session.ExpiresAt) {
		_, _ = provider.StopLearning(ctx)
		delete(s.irSessions, session.SessionID)
		s.activeIRSessionID = ""
		return IRLearningSession{}, ErrIRLearningTimeout
	}
	if session.State == "captured" && session.Capture != nil {
		return *session, nil
	}

	remote, err := provider.LearningStatus(ctx)
	if err != nil {
		var controllerErr *executor.IRControllerError
		if errors.As(err, &controllerErr) && controllerErr.StatusCode == http.StatusRequestTimeout {
			delete(s.irSessions, session.SessionID)
			s.activeIRSessionID = ""
			return IRLearningSession{}, ErrIRLearningTimeout
		}
		return IRLearningSession{}, err
	}
	if !remote.OK && remote.State != "timeout" {
		return IRLearningSession{}, fmt.Errorf("%w: learning error: %s", executor.ErrIRUnavailable, remote.Message)
	}
	switch remote.State {
	case "timeout":
		delete(s.irSessions, session.SessionID)
		s.activeIRSessionID = ""
		return IRLearningSession{}, ErrIRLearningTimeout
	case "error":
		return IRLearningSession{}, fmt.Errorf("%w: learning error: %s", executor.ErrIRUnavailable, remote.Message)
	case "idle":
		delete(s.irSessions, session.SessionID)
		s.activeIRSessionID = ""
		return IRLearningSession{}, fmt.Errorf("%w: controller left learning mode without a capture", executor.ErrIRUnavailable)
	}
	if remote.Capture == nil || remote.Capture.IsRepeat {
		session.State = "learning"
		return *session, nil
	}
	if strings.TrimSpace(remote.Capture.CaptureID) == "" {
		return IRLearningSession{}, fmt.Errorf("%w: controller returned a capture without captureId", executor.ErrIRUnavailable)
	}
	if err := executor.ValidateIRSignal(remote.Capture.Signal); err != nil {
		return IRLearningSession{}, fmt.Errorf("%w: invalid infrared capture: %v", executor.ErrIRUnavailable, err)
	}
	session.Capture = remote.Capture
	session.State = "captured"
	_, stopErr := provider.StopLearning(ctx)
	if stopErr != nil {
		return IRLearningSession{}, fmt.Errorf("stop infrared learning after capture: %w", stopErr)
	}
	return *session, nil
}

func (s *Service) ConfirmIRLearning(ctx context.Context, applianceID string, input ConfirmIRLearningInput) (domain.Action, error) {
	appliance, err := s.store.ApplianceByID(ctx, applianceID)
	if err != nil {
		return domain.Action{}, err
	}
	provider, err := s.irProviderForAppliance(appliance)
	if err != nil {
		return domain.Action{}, err
	}
	input.SessionID = strings.TrimSpace(input.SessionID)
	input.CaptureID = strings.TrimSpace(input.CaptureID)
	input.Name = strings.TrimSpace(input.Name)
	if input.SessionID == "" || input.CaptureID == "" || input.Name == "" || len([]rune(input.Name)) > 100 {
		return domain.Action{}, fmt.Errorf("%w: sessionId, captureId, and a name of at most 100 characters are required", ErrInvalidAction)
	}
	if input.Repeat == 0 {
		input.Repeat = 1
	}
	if input.Repeat < 1 || input.Repeat > 5 {
		return domain.Action{}, fmt.Errorf("%w: repeat must be between 1 and 5", ErrInvalidAction)
	}

	s.irMu.Lock()
	defer s.irMu.Unlock()
	session := s.activeSessionLocked()
	if session == nil || session.ApplianceID != applianceID || session.SessionID != input.SessionID {
		return domain.Action{}, ErrIRLearningNotFound
	}
	if !s.now().Before(session.ExpiresAt) {
		_, _ = provider.StopLearning(ctx)
		delete(s.irSessions, session.SessionID)
		s.activeIRSessionID = ""
		return domain.Action{}, ErrIRLearningTimeout
	}
	if session.State != "captured" || session.Capture == nil {
		return domain.Action{}, ErrIRLearningNotCaptured
	}
	if session.Capture.CaptureID != input.CaptureID {
		return domain.Action{}, fmt.Errorf("%w: captureId does not match the current capture", ErrIRLearningNotCaptured)
	}
	actions, err := s.store.ListActions(ctx, applianceID)
	if err != nil {
		return domain.Action{}, err
	}
	for _, action := range actions {
		if strings.EqualFold(strings.TrimSpace(action.Name), input.Name) {
			return domain.Action{}, ErrDuplicateAction
		}
	}
	params, err := json.Marshal(executor.IRParams{
		ControllerID: provider.ControllerID(),
		Signal:       session.Capture.Signal,
		Repeat:       input.Repeat,
	})
	if err != nil {
		return domain.Action{}, fmt.Errorf("encode infrared action: %w", err)
	}
	action, err := s.CreateAction(ctx, domain.CreateActionInput{
		ApplianceID:  applianceID,
		Name:         input.Name,
		ProviderType: domain.ProviderESP32IR,
		Params:       params,
	})
	if err != nil {
		return domain.Action{}, err
	}
	delete(s.irSessions, session.SessionID)
	s.activeIRSessionID = ""
	return action, nil
}

func (s *Service) StopIRLearning(ctx context.Context, applianceID, sessionID string) error {
	appliance, err := s.store.ApplianceByID(ctx, applianceID)
	if err != nil {
		return err
	}
	provider, err := s.irProviderForAppliance(appliance)
	if err != nil {
		return err
	}
	s.irMu.Lock()
	defer s.irMu.Unlock()
	session := s.activeSessionLocked()
	if session == nil || session.ApplianceID != applianceID {
		return ErrIRLearningNotFound
	}
	if strings.TrimSpace(sessionID) != "" && session.SessionID != strings.TrimSpace(sessionID) {
		return ErrIRLearningNotFound
	}
	_, stopErr := provider.StopLearning(ctx)
	delete(s.irSessions, session.SessionID)
	s.activeIRSessionID = ""
	return stopErr
}

func (s *Service) TestIR(ctx context.Context, applianceID string) error {
	appliance, err := s.store.ApplianceByID(ctx, applianceID)
	if err != nil {
		return err
	}
	provider, err := s.irProviderForAppliance(appliance)
	if err != nil {
		return err
	}
	return provider.TestSignal(ctx)
}

func (s *Service) irProviderForAppliance(appliance domain.Appliance) (executor.IRProvider, error) {
	if appliance.EffectiveControlProvider() != domain.ProviderESP32IR {
		return nil, fmt.Errorf("%w: appliance %s is not controlled by ESP32_IR", ErrInvalidAppliance, appliance.ID)
	}
	provider, err := s.executor.IRProvider()
	if err != nil {
		return nil, err
	}
	controllerID := strings.TrimSpace(appliance.ControllerID)
	if controllerID == "" {
		controllerID = provider.ControllerID()
	}
	if controllerID != provider.ControllerID() {
		return nil, fmt.Errorf("%w: unknown infrared controller %s", ErrInvalidAppliance, controllerID)
	}
	if !provider.Configured() {
		return nil, executor.ErrIRNotConfigured
	}
	return provider, nil
}

func (s *Service) activeSessionLocked() *IRLearningSession {
	if s.activeIRSessionID == "" {
		return nil
	}
	return s.irSessions[s.activeIRSessionID]
}
