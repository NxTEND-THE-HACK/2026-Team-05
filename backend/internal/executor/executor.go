package executor

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

type ActionExecutor interface {
	Execute(context.Context, domain.Action) error
	Validate(domain.Action) error
}

type Registry struct {
	tuya ActionExecutor
}

func NewRegistry(tuya ActionExecutor) *Registry {
	return &Registry{tuya: tuya}
}

func (r *Registry) Execute(ctx context.Context, action domain.Action) error {
	executor, err := r.forProvider(action.ProviderType)
	if err != nil {
		return err
	}
	return executor.Execute(ctx, action)
}

func (r *Registry) Validate(action domain.Action) error {
	if !json.Valid(action.Params) {
		return fmt.Errorf("action params must be valid JSON")
	}
	executor, err := r.forProvider(action.ProviderType)
	if err != nil {
		return err
	}
	return executor.Validate(action)
}

func (r *Registry) forProvider(provider domain.ProviderType) (ActionExecutor, error) {
	switch provider {
	case domain.ProviderTuya:
		return r.tuya, nil
	default:
		return nil, fmt.Errorf("unsupported provider type: %s", provider)
	}
}
