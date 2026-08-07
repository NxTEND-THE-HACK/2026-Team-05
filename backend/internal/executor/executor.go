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

// StateFetcher は device 状態取得能力の抽象。Tuya 以外の provider を足すときに差し替える。
type StateFetcher interface {
	GetState(ctx context.Context, deviceID, switchCode string) (DeviceState, error)
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

// GetDeviceState は provider が対応していれば現在の状態を返す。
// dry-run の場合は ErrDryRun を呼び出し側にそのまま伝搬する。
func (r *Registry) GetDeviceState(ctx context.Context, deviceID, switchCode string, provider domain.ProviderType) (DeviceState, error) {
	switch provider {
	case domain.ProviderTuya:
		fetcher, ok := r.tuya.(StateFetcher)
		if !ok {
			return DeviceState{}, fmt.Errorf("tuya executor does not support state fetching")
		}
		return fetcher.GetState(ctx, deviceID, switchCode)
	default:
		return DeviceState{}, fmt.Errorf("unsupported provider type for state: %s", provider)
	}
}

// ResolveDevice は action の params を provider 実装に解釈させて device ID / switch code を返す。
// state 取得など Execute を伴わない場面で利用する。
func (r *Registry) ResolveDevice(action domain.Action) (deviceID, switchCode string, err error) {
	switch action.ProviderType {
	case domain.ProviderTuya:
		if t, ok := r.tuya.(interface {
			ResolveDevice(domain.Action) (string, string, error)
		}); ok {
			return t.ResolveDevice(action)
		}
		return "", "", fmt.Errorf("tuya executor does not support ResolveDevice")
	default:
		return "", "", fmt.Errorf("unsupported provider type for ResolveDevice: %s", action.ProviderType)
	}
}

func (r *Registry) forProvider(provider domain.ProviderType) (ActionExecutor, error) {
	switch provider {
	case domain.ProviderTuya:
		return r.tuya, nil
	default:
		return nil, fmt.Errorf("unsupported provider type: %s", provider)
	}
}
