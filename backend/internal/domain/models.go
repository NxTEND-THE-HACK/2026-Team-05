package domain

import (
	"crypto/rand"
	"encoding/json"
	"fmt"
	"time"
)

type Camera struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	StreamURL string    `json:"streamUrl"`
	Location  string    `json:"location"`
	IsEnabled bool      `json:"isEnabled"`
	CreatedAt time.Time `json:"createdAt"`
}

type Motion struct {
	ID          string `json:"id"`
	Code        string `json:"code"`
	Name        string `json:"name"`
	Description string `json:"description"`
}

type Appliance struct {
	ID              string       `json:"id"`
	Name            string       `json:"name"`
	Category        string       `json:"category"`
	ControlProvider ProviderType `json:"controlProvider"`
	ControllerID    string       `json:"controllerId,omitempty"`
	CreatedAt       time.Time    `json:"createdAt"`
}

type ProviderType string

const (
	ProviderTuya    ProviderType = "TUYA"
	ProviderESP32IR ProviderType = "ESP32_IR"
)

// EffectiveControlProvider keeps appliances created before provider-aware
// device registration compatible with the original Tuya-only behavior.
func (a Appliance) EffectiveControlProvider() ProviderType {
	if a.ControlProvider == "" {
		return ProviderTuya
	}
	return a.ControlProvider
}

type Action struct {
	ID           string          `json:"id"`
	ApplianceID  string          `json:"applianceId"`
	Name         string          `json:"name"`
	ProviderType ProviderType    `json:"providerType"`
	Params       json.RawMessage `json:"params"`
}

type MotionBinding struct {
	ID        string    `json:"id"`
	CameraID  string    `json:"cameraId,omitempty"`
	MotionID  string    `json:"motionId"`
	ActionID  string    `json:"actionId"`
	IsEnabled bool      `json:"isEnabled"`
	CreatedAt time.Time `json:"createdAt"`
}

type ActionLogStatus string

const (
	LogSuccess     ActionLogStatus = "SUCCESS"
	LogFailed      ActionLogStatus = "FAILED"
	LogCoolingDown ActionLogStatus = "COOLING_DOWN"
)

type ActionLog struct {
	ID           string          `json:"id"`
	EventID      string          `json:"eventId"`
	CameraID     string          `json:"cameraId"`
	CameraName   string          `json:"cameraName,omitempty"`
	MotionCode   string          `json:"motionCode"`
	MotionName   string          `json:"motionName,omitempty"`
	ActionID     string          `json:"actionId,omitempty"`
	ActionName   string          `json:"actionName,omitempty"`
	Status       ActionLogStatus `json:"status"`
	ErrorMessage string          `json:"errorMessage,omitempty"`
	DetectedAt   time.Time       `json:"detectedAt"`
}

type DetectionEvent struct {
	EventID    string    `json:"event_id"`
	CameraID   string    `json:"camera_id"`
	MotionCode string    `json:"motion_code"`
	Confidence float64   `json:"confidence"`
	DetectedAt time.Time `json:"detected_at"`
}

type CreateApplianceInput struct {
	Name            string       `json:"name"`
	Category        string       `json:"category"`
	ControlProvider ProviderType `json:"controlProvider"`
	ControllerID    string       `json:"controllerId,omitempty"`
}

type CreateActionInput struct {
	ApplianceID  string          `json:"applianceId"`
	Name         string          `json:"name"`
	ProviderType ProviderType    `json:"providerType"`
	Params       json.RawMessage `json:"params"`
}

type CreateBindingInput struct {
	CameraID string `json:"cameraId,omitempty"`
	MotionID string `json:"motionId"`
	ActionID string `json:"actionId"`
}

type DetectionClaim struct {
	Duplicate bool
	Log       *ActionLog
	Action    *Action
}

func NewID(prefix string) (string, error) {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", fmt.Errorf("generate id: %w", err)
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf("%s-%x-%x-%x-%x-%x", prefix, value[0:4], value[4:6], value[6:8], value[8:10], value[10:16]), nil
}
