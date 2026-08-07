package store

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

func TestMemoryClaimDetectionIsIdempotentAndEnforcesCooldown(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	repository := NewMemory(DefaultSeed(now))
	if _, err := repository.CreateBinding(context.Background(), domain.CreateBindingInput{
		MotionID: "motion-pose-right-hand-up", ActionID: "action-plug-a-on",
	}); err != nil {
		t.Fatalf("CreateBinding() error = %v", err)
	}
	event := domain.DetectionEvent{EventID: "event-1", CameraID: "demo-camera-1", MotionCode: "POSE_RIGHT_HAND_UP", Confidence: .9, DetectedAt: now}

	claim, err := repository.ClaimDetection(context.Background(), event, 5*time.Second, now)
	if err != nil {
		t.Fatalf("first ClaimDetection() error = %v", err)
	}
	if claim.Action == nil || claim.Action.ID != "action-plug-a-on" {
		t.Fatalf("first claim = %+v, want plug A on action", claim)
	}

	duplicate, err := repository.ClaimDetection(context.Background(), event, 5*time.Second, now)
	if err != nil || !duplicate.Duplicate {
		t.Fatalf("duplicate claim = %+v, error = %v", duplicate, err)
	}

	event.EventID = "event-2"
	cooling, err := repository.ClaimDetection(context.Background(), event, 5*time.Second, now.Add(time.Second))
	if err != nil {
		t.Fatalf("cooling ClaimDetection() error = %v", err)
	}
	if cooling.Log == nil || cooling.Log.Status != domain.LogCoolingDown || cooling.Action != nil {
		t.Fatalf("cooling claim = %+v", cooling)
	}

	event.EventID = "event-3"
	ready, err := repository.ClaimDetection(context.Background(), event, 5*time.Second, now.Add(5*time.Second))
	if err != nil || ready.Action == nil {
		t.Fatalf("ready claim = %+v, error = %v", ready, err)
	}
}

func TestMemoryCreateBindingUpdatesExistingMotion(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	repository := NewMemory(DefaultSeed(now))

	created, err := repository.CreateBinding(context.Background(), domain.CreateBindingInput{
		CameraID: "demo-camera-1", MotionID: "motion-pose-right-hand-up", ActionID: "action-plug-a-on",
	})
	if err != nil {
		t.Fatalf("first CreateBinding() error = %v", err)
	}
	binding, err := repository.CreateBinding(context.Background(), domain.CreateBindingInput{
		CameraID: "demo-camera-2", MotionID: "motion-pose-right-hand-up", ActionID: "action-plug-c-on",
	})
	if err != nil {
		t.Fatalf("CreateBinding() error = %v", err)
	}
	if binding.ID != created.ID || binding.CameraID != "demo-camera-2" || binding.ActionID != "action-plug-c-on" {
		t.Fatalf("binding = %+v, want existing binding updated", binding)
	}
}

func TestMemoryDeleteBinding(t *testing.T) {
	repository := NewMemory(DefaultSeed(time.Now()))
	binding, err := repository.CreateBinding(context.Background(), domain.CreateBindingInput{
		MotionID: "motion-pose-right-hand-up", ActionID: "action-plug-a-on",
	})
	if err != nil {
		t.Fatalf("CreateBinding() error = %v", err)
	}

	if err := repository.DeleteBinding(context.Background(), binding.ID); err != nil {
		t.Fatalf("DeleteBinding() error = %v", err)
	}
	items, err := repository.ListBindings(context.Background())
	if err != nil {
		t.Fatalf("ListBindings() error = %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("bindings = %+v, want no bindings", items)
	}
	if err := repository.DeleteBinding(context.Background(), binding.ID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("second DeleteBinding() error = %v, want ErrNotFound", err)
	}
}

func TestMemoryMotionBindingAppliesAcrossCameras(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	repository := NewMemory(DefaultSeed(now))
	if _, err := repository.CreateBinding(context.Background(), domain.CreateBindingInput{
		CameraID: "demo-camera-1", MotionID: "motion-pose-right-hand-up", ActionID: "action-plug-c-on",
	}); err != nil {
		t.Fatalf("CreateBinding() error = %v", err)
	}
	event := domain.DetectionEvent{EventID: "event-camera-2", CameraID: "demo-camera-2", MotionCode: "POSE_RIGHT_HAND_UP", Confidence: .9, DetectedAt: now}

	claim, err := repository.ClaimDetection(context.Background(), event, 5*time.Second, now)
	if err != nil {
		t.Fatalf("ClaimDetection() error = %v", err)
	}
	if claim.Action == nil || claim.Action.ID != "action-plug-c-on" {
		t.Fatalf("claim = %+v, want global motion action", claim)
	}
}

func TestMemoryHasNoImplicitCameraToDeviceBinding(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	repository := NewMemory(DefaultSeed(now))
	event := domain.DetectionEvent{EventID: "event-unbound", CameraID: "demo-camera-1", MotionCode: "POSE_RIGHT_HAND_UP", Confidence: .9, DetectedAt: now}

	claim, err := repository.ClaimDetection(context.Background(), event, 5*time.Second, now)
	if err != nil {
		t.Fatalf("ClaimDetection() error = %v", err)
	}
	if claim.Action != nil || claim.Log == nil || claim.Log.Status != domain.LogFailed || claim.Log.ErrorMessage != "motion binding was not found" {
		t.Fatalf("claim = %+v, want unbound detection without an action", claim)
	}
}

func TestMemorySeedContainsEveryRecognitionMotion(t *testing.T) {
	repository := NewMemory(DefaultSeed(time.Now()))
	motions, err := repository.ListMotions(context.Background())
	if err != nil {
		t.Fatalf("ListMotions() error = %v", err)
	}

	want := map[string]bool{
		"POSE_RIGHT_HAND_UP": false,
		"POSE_LEFT_HAND_UP": false,
		"MOTION_SWIPE_RIGHT": false,
		"MOTION_SWIPE_LEFT": false,
		"MOTION_FINGER_SNAP": false,
		"MOTION_THUMBS_UP_MOVE_UP": false,
		"MOTION_THUMBS_DOWN_MOVE_DOWN": false,
		"MOTION_CLAP": false,
		"MOTION_OPEN_TO_FIST_DOWN": false,
		"MOTION_HAND_ROTATE_RIGHT": false,
		"MOTION_HAND_ROTATE_LEFT": false,
	}
	for _, motion := range motions {
		if _, ok := want[motion.Code]; ok {
			want[motion.Code] = true
		}
	}
	for code, found := range want {
		if !found {
			t.Errorf("motion %q is missing from the backend seed", code)
		}
	}
}

func TestMemoryRejectsUnknownDetection(t *testing.T) {
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	repository := NewMemory(DefaultSeed(now))
	event := domain.DetectionEvent{EventID: "event-unknown", CameraID: "missing", MotionCode: "POSE_RIGHT_HAND_UP", DetectedAt: now}

	claim, err := repository.ClaimDetection(context.Background(), event, 5*time.Second, now)
	if err != nil {
		t.Fatalf("ClaimDetection() error = %v", err)
	}
	if claim.Log == nil || claim.Log.Status != domain.LogFailed {
		t.Fatalf("claim = %+v, want failed log", claim)
	}
}
