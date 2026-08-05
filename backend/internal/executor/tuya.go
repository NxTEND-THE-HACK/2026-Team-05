package executor

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"regexp"
	"strings"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/config"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/tuya/tuya-connector-go/connector"
	"github.com/tuya/tuya-connector-go/connector/env"
	"github.com/tuya/tuya-connector-go/connector/httplib"
)

var (
	deviceIDPattern   = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)
	switchCodePattern = regexp.MustCompile(`^[A-Za-z0-9_]+$`)
)

type Tuya struct {
	dryRun    bool
	deviceIDs map[string]string
	logger    *slog.Logger
}

type TuyaParams struct {
	DeviceID    string `json:"deviceId"`
	DeviceIDEnv string `json:"deviceIdEnv"`
	SwitchCode  string `json:"switchCode"`
	Value       *bool  `json:"value"`
}

type tuyaResponse struct {
	Code    int    `json:"code"`
	Message string `json:"msg"`
	Success bool   `json:"success"`
	Result  bool   `json:"result"`
}

func NewTuya(cfg config.TuyaConfig, logger *slog.Logger) (*Tuya, error) {
	apiHost, messageHost, err := tuyaHosts(cfg.Region)
	if err != nil {
		return nil, err
	}
	if !cfg.DryRun {
		connector.InitWithOptions(
			env.WithApiHost(apiHost),
			env.WithMsgHost(messageHost),
			env.WithAccessID(cfg.AccessID),
			env.WithAccessKey(cfg.SecretKey),
			env.WithDebugMode(cfg.Debug),
		)
	}
	return &Tuya{dryRun: cfg.DryRun, deviceIDs: cfg.DeviceIDs, logger: logger}, nil
}

func (t *Tuya) Validate(action domain.Action) error {
	_, _, _, err := t.command(action)
	return err
}

func (t *Tuya) Execute(ctx context.Context, action domain.Action) error {
	deviceID, switchCode, value, err := t.command(action)
	if err != nil {
		return err
	}
	if t.dryRun {
		t.logger.Info("Tuya dry-run command", "action_id", action.ID, "device_id", deviceID, "switch_code", switchCode, "value", value)
		return nil
	}

	payload, err := json.Marshal(map[string]any{
		"commands": []map[string]any{{"code": switchCode, "value": value}},
	})
	if err != nil {
		return fmt.Errorf("encode Tuya command: %w", err)
	}
	response := tuyaResponse{}
	err = connector.MakePostRequest(
		ctx,
		connector.WithAPIUri(fmt.Sprintf("/v1.0/iot-03/devices/%s/commands", deviceID)),
		connector.WithPayload(payload),
		connector.WithResp(&response),
	)
	if err != nil {
		return fmt.Errorf("send Tuya command: %w", err)
	}
	if !response.Success || !response.Result {
		return fmt.Errorf("Tuya rejected command: code=%d message=%s", response.Code, response.Message)
	}
	t.logger.Info("Tuya command succeeded", "action_id", action.ID, "device_id", deviceID, "value", value)
	return nil
}

func (t *Tuya) command(action domain.Action) (string, string, bool, error) {
	var params TuyaParams
	decoder := json.NewDecoder(bytes.NewReader(action.Params))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&params); err != nil {
		return "", "", false, fmt.Errorf("decode Tuya params: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return "", "", false, fmt.Errorf("Tuya params must contain one JSON object")
	}
	if params.DeviceID != "" && params.DeviceIDEnv != "" {
		return "", "", false, fmt.Errorf("use either deviceId or deviceIdEnv, not both")
	}
	deviceID := strings.TrimSpace(params.DeviceID)
	if deviceID == "" && params.DeviceIDEnv != "" {
		var ok bool
		deviceID, ok = t.deviceIDs[params.DeviceIDEnv]
		if !ok {
			return "", "", false, fmt.Errorf("deviceIdEnv is not allowed: %s", params.DeviceIDEnv)
		}
		if deviceID == "" && t.dryRun {
			deviceID = "dry-run:" + params.DeviceIDEnv
		}
	}
	if deviceID == "" {
		return "", "", false, fmt.Errorf("Tuya device ID is not configured")
	}
	if !deviceIDPattern.MatchString(strings.TrimPrefix(deviceID, "dry-run:")) {
		return "", "", false, fmt.Errorf("Tuya device ID contains invalid characters")
	}
	switchCode := strings.TrimSpace(params.SwitchCode)
	if switchCode == "" {
		switchCode = "switch"
	}
	if !switchCodePattern.MatchString(switchCode) {
		return "", "", false, fmt.Errorf("Tuya switchCode contains invalid characters")
	}
	if params.Value == nil {
		return "", "", false, fmt.Errorf("Tuya params.value is required")
	}
	return deviceID, switchCode, *params.Value, nil
}

func tuyaHosts(region string) (string, string, error) {
	switch region {
	case "cn":
		return httplib.URL_CN, httplib.MSG_CN, nil
	case "us":
		return httplib.URL_US, httplib.MSG_US, nil
	case "eu":
		return httplib.URL_EU, httplib.MSG_EU, nil
	case "in":
		return httplib.URL_IN, httplib.MSG_IN, nil
	case "jp":
		return "https://openapi.tuyajp.com", "pulsar+ssl://mqe.tuyajp.com:7285/", nil
	default:
		return "", "", fmt.Errorf("unsupported Tuya region: %s", region)
	}
}
