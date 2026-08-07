package service

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/executor"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/store"
)

type stateTestExecutor struct {
	states map[string]executor.DeviceState
	calls  []string
}

func (e *stateTestExecutor) Execute(context.Context, domain.Action) error { return nil }
func (e *stateTestExecutor) Validate(domain.Action) error                 { return nil }

func (e *stateTestExecutor) ResolveDevice(action domain.Action) (string, string, error) {
	var params struct {
		DeviceID   string `json:"deviceId"`
		SwitchCode string `json:"switchCode"`
	}
	if err := json.Unmarshal(action.Params, &params); err != nil {
		return "", "", err
	}
	if params.SwitchCode == "" {
		params.SwitchCode = "switch"
	}
	return params.DeviceID, params.SwitchCode, nil
}

func (e *stateTestExecutor) GetState(_ context.Context, deviceID, switchCode string) (executor.DeviceState, error) {
	key := fmt.Sprintf("%s::%s", deviceID, switchCode)
	e.calls = append(e.calls, key)
	state, ok := e.states[key]
	if !ok {
		return executor.DeviceState{}, fmt.Errorf("state not found: %s", key)
	}
	return state, nil
}

func TestGetApplianceStateReturnsStateForEachSwitchCode(t *testing.T) {
	repository := store.NewMemory(store.SeedData{
		Appliances: []domain.Appliance{{ID: "appliance-1"}},
		Actions: []domain.Action{
			{ID: "action-1-on", ApplianceID: "appliance-1", ProviderType: domain.ProviderTuya, Params: stateParams("device-1", "switch_1")},
			{ID: "action-1-off", ApplianceID: "appliance-1", ProviderType: domain.ProviderTuya, Params: stateParams("device-1", "switch_1")},
			{ID: "action-2-on", ApplianceID: "appliance-1", ProviderType: domain.ProviderTuya, Params: stateParams("device-1", "switch_2")},
			{ID: "action-2-off", ApplianceID: "appliance-1", ProviderType: domain.ProviderTuya, Params: stateParams("device-1", "switch_2")},
		},
	})
	on := true
	off := false
	provider := &stateTestExecutor{states: map[string]executor.DeviceState{
		"device-1::switch_1": {Online: true, SwitchCode: "switch_1", Value: &on},
		"device-1::switch_2": {Online: true, SwitchCode: "switch_2", Value: &off},
	}}
	appService := New(repository, executor.NewRegistry(provider), 0)

	state, err := appService.GetApplianceState(context.Background(), "appliance-1")
	if err != nil {
		t.Fatalf("GetApplianceState() error = %v", err)
	}
	if len(state.States) != 2 {
		t.Fatalf("states = %+v, want one state per switchCode", state.States)
	}
	if state.Value != nil || state.SwitchCode != "" {
		t.Fatalf("top-level state = %+v, want unknown aggregate state", state)
	}

	byCode := make(map[string]ApplianceSwitchState, len(state.States))
	for _, item := range state.States {
		byCode[item.SwitchCode] = item
	}
	if byCode["switch_1"].Value == nil || *byCode["switch_1"].Value != true {
		t.Fatalf("switch_1 state = %+v, want ON", byCode["switch_1"])
	}
	if byCode["switch_2"].Value == nil || *byCode["switch_2"].Value != false {
		t.Fatalf("switch_2 state = %+v, want OFF", byCode["switch_2"])
	}
	if len(provider.calls) != 2 {
		t.Fatalf("GetState calls = %v, want duplicate ON/OFF actions deduplicated", provider.calls)
	}
}

func stateParams(deviceID, switchCode string) json.RawMessage {
	value, _ := json.Marshal(map[string]string{"deviceId": deviceID, "switchCode": switchCode})
	return value
}
