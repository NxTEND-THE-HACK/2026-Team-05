package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/service"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/store"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
)

type Handler struct {
	store   store.Store
	service *service.Service
	logger  *slog.Logger
}

func New(repository store.Store, appService *service.Service, logger *slog.Logger, allowedOrigins []string) *echo.Echo {
	h := &Handler{store: repository, service: appService, logger: logger}
	e := echo.New()
	e.HideBanner = true
	e.HTTPErrorHandler = h.errorHandler
	e.Use(middleware.RequestID())
	e.Use(middleware.Recover())
	e.Use(middleware.BodyLimit("1M"))
	e.Use(middleware.CORSWithConfig(middleware.CORSConfig{
		AllowOrigins: allowedOrigins,
		AllowMethods: []string{http.MethodGet, http.MethodPost, http.MethodOptions},
		AllowHeaders: []string{echo.HeaderOrigin, echo.HeaderContentType, echo.HeaderAccept},
	}))

	e.GET("/healthz", h.health)
	e.POST("/internal/detections", h.detection)

	api := e.Group("/api")
	api.GET("/cameras", h.cameras)
	api.GET("/motions", h.motions)
	api.GET("/appliances", h.appliances)
	api.POST("/appliances", h.createAppliance)
	api.GET("/appliances/:id/state", h.applianceState)
	api.GET("/actions", h.actions)
	api.POST("/actions", h.createAction)
	api.POST("/actions/:id/execute", h.executeAction)
	api.GET("/bindings", h.bindings)
	api.POST("/bindings", h.createBinding)
	api.GET("/logs", h.logs)
	return e
}

func (h *Handler) health(c echo.Context) error {
	ctx, cancel := context.WithTimeout(c.Request().Context(), 2*time.Second)
	defer cancel()
	if err := h.store.Health(ctx); err != nil {
		return echo.NewHTTPError(http.StatusServiceUnavailable, "storage is unavailable").SetInternal(err)
	}
	return c.JSON(http.StatusOK, map[string]string{"status": "ok"})
}

func (h *Handler) detection(c echo.Context) error {
	var input domain.DetectionEvent
	if err := bindStrict(c, &input); err != nil {
		return err
	}
	if err := validateDetection(input); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, err.Error())
	}
	ctx, cancel := context.WithTimeout(c.Request().Context(), 10*time.Second)
	defer cancel()
	result, err := h.service.ProcessDetection(ctx, input)
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, result)
}

func (h *Handler) cameras(c echo.Context) error {
	items, err := h.store.ListCameras(c.Request().Context())
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, map[string]any{"cameras": items})
}

func (h *Handler) motions(c echo.Context) error {
	items, err := h.store.ListMotions(c.Request().Context())
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, map[string]any{"motions": items})
}

func (h *Handler) appliances(c echo.Context) error {
	items, err := h.store.ListAppliances(c.Request().Context())
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, map[string]any{"appliances": items})
}

func (h *Handler) applianceState(c echo.Context) error {
	id := strings.TrimSpace(c.Param("id"))
	if id == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "id is required")
	}
	if _, err := h.store.ApplianceByID(c.Request().Context(), id); err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(c.Request().Context(), 6*time.Second)
	defer cancel()
	state, err := h.service.GetApplianceState(ctx, id)
	if err != nil {
		// Tuya 側の障害でも UI を生かしたいため、value=null で返して error フィールドに理由を入れる。
		state.Error = err.Error()
		return c.JSON(http.StatusOK, state)
	}
	return c.JSON(http.StatusOK, state)
}

func (h *Handler) createAppliance(c echo.Context) error {
	var input domain.CreateApplianceInput
	if err := bindStrict(c, &input); err != nil {
		return err
	}
	input.Name = strings.TrimSpace(input.Name)
	input.Category = strings.TrimSpace(input.Category)
	if input.Name == "" || input.Category == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "name and category are required")
	}
	item, err := h.store.CreateAppliance(c.Request().Context(), input)
	if err != nil {
		return err
	}
	return c.JSON(http.StatusCreated, item)
}

func (h *Handler) actions(c echo.Context) error {
	items, err := h.store.ListActions(c.Request().Context(), strings.TrimSpace(c.QueryParam("applianceId")))
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, map[string]any{"actions": items})
}

func (h *Handler) createAction(c echo.Context) error {
	var input domain.CreateActionInput
	if err := bindStrict(c, &input); err != nil {
		return err
	}
	input.ApplianceID = strings.TrimSpace(input.ApplianceID)
	input.Name = strings.TrimSpace(input.Name)
	if input.ApplianceID == "" || input.Name == "" || input.ProviderType == "" || len(input.Params) == 0 {
		return echo.NewHTTPError(http.StatusBadRequest, "applianceId, name, providerType, and params are required")
	}
	item, err := h.service.CreateAction(c.Request().Context(), input)
	if err != nil {
		return err
	}
	return c.JSON(http.StatusCreated, item)
}

func (h *Handler) executeAction(c echo.Context) error {
	ctx, cancel := context.WithTimeout(c.Request().Context(), 10*time.Second)
	defer cancel()
	result, err := h.service.ExecuteAction(ctx, c.Param("id"))
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, result)
}

func (h *Handler) bindings(c echo.Context) error {
	items, err := h.store.ListBindings(c.Request().Context())
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, map[string]any{"bindings": items})
}

func (h *Handler) createBinding(c echo.Context) error {
	var input domain.CreateBindingInput
	if err := bindStrict(c, &input); err != nil {
		return err
	}
	input.CameraID = strings.TrimSpace(input.CameraID)
	input.MotionID = strings.TrimSpace(input.MotionID)
	input.ActionID = strings.TrimSpace(input.ActionID)
	if input.MotionID == "" || input.ActionID == "" {
		return echo.NewHTTPError(http.StatusBadRequest, "motionId and actionId are required")
	}
	item, err := h.store.CreateBinding(c.Request().Context(), input)
	if err != nil {
		return err
	}
	return c.JSON(http.StatusCreated, item)
}

func (h *Handler) logs(c echo.Context) error {
	limit := 100
	if raw := c.QueryParam("limit"); raw != "" {
		value, err := strconv.Atoi(raw)
		if err != nil || value < 1 || value > 500 {
			return echo.NewHTTPError(http.StatusBadRequest, "limit must be between 1 and 500")
		}
		limit = value
	}
	items, err := h.store.ListLogs(c.Request().Context(), limit)
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, map[string]any{"logs": items})
}

func (h *Handler) errorHandler(err error, c echo.Context) {
	if c.Response().Committed {
		return
	}
	status := http.StatusInternalServerError
	message := "internal server error"
	var httpErr *echo.HTTPError
	if errors.As(err, &httpErr) {
		status = httpErr.Code
		message = fmt.Sprint(httpErr.Message)
	} else if errors.Is(err, store.ErrNotFound) {
		status = http.StatusNotFound
		message = "resource not found"
	} else if errors.Is(err, store.ErrConflict) {
		status = http.StatusConflict
		message = "resource already exists"
	} else if errors.Is(err, service.ErrInvalidAction) {
		status = http.StatusBadRequest
		message = err.Error()
	}
	if status >= 500 {
		h.logger.Error("request failed", "request_id", c.Response().Header().Get(echo.HeaderXRequestID), "method", c.Request().Method, "path", c.Path(), "error", err)
	}
	_ = c.JSON(status, map[string]string{"error": message})
}

func bindStrict(c echo.Context, target any) error {
	request := c.Request()
	if !strings.HasPrefix(request.Header.Get(echo.HeaderContentType), echo.MIMEApplicationJSON) {
		return echo.NewHTTPError(http.StatusUnsupportedMediaType, "Content-Type must be application/json")
	}
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return echo.NewHTTPError(http.StatusBadRequest, "invalid JSON body").SetInternal(err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return echo.NewHTTPError(http.StatusBadRequest, "request body must contain one JSON object")
	}
	return nil
}

func validateDetection(input domain.DetectionEvent) error {
	if strings.TrimSpace(input.EventID) == "" || len(input.EventID) > 128 {
		return errors.New("event_id is required and must be at most 128 characters")
	}
	if strings.TrimSpace(input.CameraID) == "" || strings.TrimSpace(input.MotionCode) == "" {
		return errors.New("camera_id and motion_code are required")
	}
	if input.Confidence < 0 || input.Confidence > 1 {
		return errors.New("confidence must be between 0 and 1")
	}
	if input.DetectedAt.IsZero() {
		return errors.New("detected_at is required")
	}
	return nil
}
