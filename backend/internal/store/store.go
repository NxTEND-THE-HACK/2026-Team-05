package store

import (
	"context"
	"errors"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

var (
	ErrNotFound = errors.New("not found")
	ErrConflict = errors.New("conflict")
)

type Store interface {
	Health(context.Context) error
	Close()

	ListCameras(context.Context) ([]domain.Camera, error)
	ListMotions(context.Context) ([]domain.Motion, error)
	ListAppliances(context.Context) ([]domain.Appliance, error)
	ListActions(context.Context, string) ([]domain.Action, error)
	ListBindings(context.Context) ([]domain.MotionBinding, error)
	ListLogs(context.Context, int) ([]domain.ActionLog, error)

	CreateAppliance(context.Context, domain.CreateApplianceInput) (domain.Appliance, error)
	CreateAction(context.Context, domain.CreateActionInput) (domain.Action, error)
	CreateBinding(context.Context, domain.CreateBindingInput) (domain.MotionBinding, error)
	DeleteAction(context.Context, string) error
	DeleteBinding(context.Context, string) error
	ActionByID(context.Context, string) (domain.Action, error)
	ApplianceByID(context.Context, string) (domain.Appliance, error)

	ClaimDetection(context.Context, domain.DetectionEvent, time.Duration, time.Time) (domain.DetectionClaim, error)
	AppendLog(context.Context, domain.ActionLog) (domain.ActionLog, error)
}
