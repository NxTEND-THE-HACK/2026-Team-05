package store

import (
	"context"
	"fmt"
	"sort"
	"sync"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

type Memory struct {
	mu           sync.RWMutex
	cameras      map[string]domain.Camera
	motions      map[string]domain.Motion
	appliances   map[string]domain.Appliance
	actions      map[string]domain.Action
	bindings     map[string]domain.MotionBinding
	logs         []domain.ActionLog
	processed    map[string]struct{}
	lastExecuted map[string]time.Time
}

func NewMemory(seed SeedData) *Memory {
	m := &Memory{
		cameras:      make(map[string]domain.Camera),
		motions:      make(map[string]domain.Motion),
		appliances:   make(map[string]domain.Appliance),
		actions:      make(map[string]domain.Action),
		bindings:     make(map[string]domain.MotionBinding),
		processed:    make(map[string]struct{}),
		lastExecuted: make(map[string]time.Time),
	}
	for _, value := range seed.Cameras {
		m.cameras[value.ID] = value
	}
	for _, value := range seed.Motions {
		m.motions[value.ID] = value
	}
	for _, value := range seed.Appliances {
		m.appliances[value.ID] = value
	}
	for _, value := range seed.Actions {
		m.actions[value.ID] = value
	}
	for _, value := range seed.Bindings {
		m.bindings[value.ID] = value
	}
	return m
}

func (m *Memory) Health(context.Context) error { return nil }
func (m *Memory) Close()                       {}

func (m *Memory) ListCameras(context.Context) ([]domain.Camera, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	items := make([]domain.Camera, 0, len(m.cameras))
	for _, item := range m.cameras {
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].CreatedAt.Before(items[j].CreatedAt) })
	return items, nil
}

func (m *Memory) ListMotions(context.Context) ([]domain.Motion, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	items := make([]domain.Motion, 0, len(m.motions))
	for _, item := range m.motions {
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].ID < items[j].ID })
	return items, nil
}

func (m *Memory) ListAppliances(context.Context) ([]domain.Appliance, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	items := make([]domain.Appliance, 0, len(m.appliances))
	for _, item := range m.appliances {
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].CreatedAt.Before(items[j].CreatedAt) })
	return items, nil
}

func (m *Memory) ListActions(_ context.Context, applianceID string) ([]domain.Action, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	items := make([]domain.Action, 0, len(m.actions))
	for _, item := range m.actions {
		if applianceID == "" || item.ApplianceID == applianceID {
			items = append(items, item)
		}
	}
	sort.Slice(items, func(i, j int) bool { return items[i].ID < items[j].ID })
	return items, nil
}

func (m *Memory) ListBindings(context.Context) ([]domain.MotionBinding, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	items := make([]domain.MotionBinding, 0, len(m.bindings))
	for _, item := range m.bindings {
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].CreatedAt.Before(items[j].CreatedAt) })
	return items, nil
}

func (m *Memory) ListLogs(_ context.Context, limit int) ([]domain.ActionLog, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if limit > len(m.logs) {
		limit = len(m.logs)
	}
	items := make([]domain.ActionLog, limit)
	copy(items, m.logs[:limit])
	return items, nil
}

func (m *Memory) CreateAppliance(_ context.Context, input domain.CreateApplianceInput) (domain.Appliance, error) {
	id, err := domain.NewID("appliance")
	if err != nil {
		return domain.Appliance{}, err
	}
	item := domain.Appliance{ID: id, Name: input.Name, Category: input.Category, CreatedAt: time.Now().UTC()}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.appliances[item.ID] = item
	return item, nil
}

func (m *Memory) CreateAction(_ context.Context, input domain.CreateActionInput) (domain.Action, error) {
	id, err := domain.NewID("action")
	if err != nil {
		return domain.Action{}, err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.appliances[input.ApplianceID]; !ok {
		return domain.Action{}, fmt.Errorf("appliance: %w", ErrNotFound)
	}
	item := domain.Action{ID: id, ApplianceID: input.ApplianceID, Name: input.Name, ProviderType: input.ProviderType, Params: input.Params}
	m.actions[item.ID] = item
	return item, nil
}

func (m *Memory) CreateBinding(_ context.Context, input domain.CreateBindingInput) (domain.MotionBinding, error) {
	id, err := domain.NewID("binding")
	if err != nil {
		return domain.MotionBinding{}, err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if input.CameraID != "" {
		if _, ok := m.cameras[input.CameraID]; !ok {
			return domain.MotionBinding{}, fmt.Errorf("camera: %w", ErrNotFound)
		}
	}
	if _, ok := m.motions[input.MotionID]; !ok {
		return domain.MotionBinding{}, fmt.Errorf("motion: %w", ErrNotFound)
	}
	if _, ok := m.actions[input.ActionID]; !ok {
		return domain.MotionBinding{}, fmt.Errorf("action: %w", ErrNotFound)
	}
	for _, item := range m.bindings {
		if item.MotionID == input.MotionID {
			item.CameraID = input.CameraID
			item.ActionID = input.ActionID
			item.IsEnabled = true
			m.bindings[item.ID] = item
			delete(m.lastExecuted, item.ID)
			return item, nil
		}
	}
	item := domain.MotionBinding{ID: id, CameraID: input.CameraID, MotionID: input.MotionID, ActionID: input.ActionID, IsEnabled: true, CreatedAt: time.Now().UTC()}
	m.bindings[item.ID] = item
	return item, nil
}

func (m *Memory) DeleteBinding(_ context.Context, id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.bindings[id]; !ok {
		return ErrNotFound
	}
	delete(m.bindings, id)
	delete(m.lastExecuted, id)
	return nil
}

func (m *Memory) ActionByID(_ context.Context, id string) (domain.Action, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	item, ok := m.actions[id]
	if !ok {
		return domain.Action{}, ErrNotFound
	}
	return item, nil
}

func (m *Memory) ApplianceByID(_ context.Context, id string) (domain.Appliance, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	item, ok := m.appliances[id]
	if !ok {
		return domain.Appliance{}, ErrNotFound
	}
	return item, nil
}

func (m *Memory) ClaimDetection(_ context.Context, event domain.DetectionEvent, cooldown time.Duration, now time.Time) (domain.DetectionClaim, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, exists := m.processed[event.EventID]; exists {
		return domain.DetectionClaim{Duplicate: true}, nil
	}
	m.processed[event.EventID] = struct{}{}

	camera, cameraOK := m.cameras[event.CameraID]
	var motion domain.Motion
	motionOK := false
	for _, candidate := range m.motions {
		if candidate.Code == event.MotionCode {
			motion, motionOK = candidate, true
			break
		}
	}
	if !cameraOK || !camera.IsEnabled || !motionOK {
		message := "camera or motion is not registered or enabled"
		log, err := m.appendLogLocked(domain.ActionLog{EventID: event.EventID, CameraID: event.CameraID, MotionCode: event.MotionCode, Status: domain.LogFailed, ErrorMessage: message, DetectedAt: event.DetectedAt})
		return domain.DetectionClaim{Log: &log}, err
	}

	var binding domain.MotionBinding
	bindingOK := false
	for _, candidate := range m.bindings {
		if candidate.MotionID == motion.ID && candidate.IsEnabled {
			binding, bindingOK = candidate, true
			break
		}
	}
	if !bindingOK {
		log, err := m.appendLogLocked(domain.ActionLog{EventID: event.EventID, CameraID: camera.ID, CameraName: camera.Name, MotionCode: motion.Code, MotionName: motion.Name, Status: domain.LogFailed, ErrorMessage: "motion binding was not found", DetectedAt: event.DetectedAt})
		return domain.DetectionClaim{Log: &log}, err
	}
	action := m.actions[binding.ActionID]
	baseLog := domain.ActionLog{EventID: event.EventID, CameraID: camera.ID, CameraName: camera.Name, MotionCode: motion.Code, MotionName: motion.Name, ActionID: action.ID, ActionName: action.Name, DetectedAt: event.DetectedAt}
	if last, exists := m.lastExecuted[binding.ID]; exists && now.Before(last.Add(cooldown)) {
		baseLog.Status = domain.LogCoolingDown
		log, err := m.appendLogLocked(baseLog)
		return domain.DetectionClaim{Log: &log}, err
	}
	m.lastExecuted[binding.ID] = now
	return domain.DetectionClaim{Action: &action, Log: &baseLog}, nil
}

func (m *Memory) AppendLog(_ context.Context, input domain.ActionLog) (domain.ActionLog, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.appendLogLocked(input)
}

func (m *Memory) appendLogLocked(input domain.ActionLog) (domain.ActionLog, error) {
	id, err := domain.NewID("log")
	if err != nil {
		return domain.ActionLog{}, err
	}
	input.ID = id
	m.logs = append([]domain.ActionLog{input}, m.logs...)
	return input, nil
}
