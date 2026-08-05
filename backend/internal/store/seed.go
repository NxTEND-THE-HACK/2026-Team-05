package store

import (
	"encoding/json"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

type SeedData struct {
	Cameras    []domain.Camera
	Motions    []domain.Motion
	Appliances []domain.Appliance
	Actions    []domain.Action
	Bindings   []domain.MotionBinding
}

func DefaultSeed(now time.Time) SeedData {
	now = now.UTC()
	params := func(deviceEnv string, on bool) json.RawMessage {
		value, _ := json.Marshal(map[string]any{
			"deviceIdEnv": deviceEnv,
			"switchCode":  "switch",
			"value":       on,
		})
		return value
	}

	return SeedData{
		Cameras: []domain.Camera{
			{ID: "demo-camera-1", Name: "カメラ1", Location: "デモエリア1", IsEnabled: true, CreatedAt: now},
			{ID: "demo-camera-2", Name: "カメラ2", Location: "デモエリア2", IsEnabled: true, CreatedAt: now},
		},
		Motions: []domain.Motion{
			{ID: "motion-pose-right-hand-up", Code: "POSE_RIGHT_HAND_UP", Name: "右手上げ", Description: "右手首を右肩より上で0.6秒保持"},
			{ID: "motion-swipe-right", Code: "MOTION_SWIPE_RIGHT", Name: "右スワイプ", Description: "右手を右方向へスワイプ"},
		},
		Appliances: []domain.Appliance{
			{ID: "appliance-plug-a", Name: "スマートプラグA", Category: "スマートプラグ", CreatedAt: now},
			{ID: "appliance-plug-b", Name: "スマートプラグB", Category: "スマートプラグ", CreatedAt: now},
			{ID: "appliance-plug-c", Name: "スマートプラグC", Category: "スマートプラグ", CreatedAt: now},
		},
		Actions: []domain.Action{
			{ID: "action-plug-a-on", ApplianceID: "appliance-plug-a", Name: "プラグA オン", ProviderType: domain.ProviderTuya, Params: params("PLUG_A_ID", true)},
			{ID: "action-plug-a-off", ApplianceID: "appliance-plug-a", Name: "プラグA オフ", ProviderType: domain.ProviderTuya, Params: params("PLUG_A_ID", false)},
			{ID: "action-plug-b-on", ApplianceID: "appliance-plug-b", Name: "プラグB オン", ProviderType: domain.ProviderTuya, Params: params("PLUG_B_ID", true)},
			{ID: "action-plug-b-off", ApplianceID: "appliance-plug-b", Name: "プラグB オフ", ProviderType: domain.ProviderTuya, Params: params("PLUG_B_ID", false)},
			{ID: "action-plug-c-on", ApplianceID: "appliance-plug-c", Name: "プラグC オン", ProviderType: domain.ProviderTuya, Params: params("PLUG_C_ID", true)},
			{ID: "action-plug-c-off", ApplianceID: "appliance-plug-c", Name: "プラグC オフ", ProviderType: domain.ProviderTuya, Params: params("PLUG_C_ID", false)},
		},
	}
}
