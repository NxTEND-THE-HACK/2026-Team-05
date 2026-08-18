package events

import (
	"testing"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

func TestLogHubClosesFullSubscription(t *testing.T) {
	hub := NewLogHub()
	subscription := hub.Subscribe()
	defer subscription.Close()

	for i := 0; i < logSubscriberBuffer; i++ {
		hub.Publish(domain.ActionLog{ID: string(rune('a' + i))})
	}
	hub.Publish(domain.ActionLog{ID: "overflow"})

	for i := 0; i < logSubscriberBuffer; i++ {
		if _, ok := <-subscription.Events; !ok {
			t.Fatalf("subscription closed before buffered log %d", i)
		}
	}
	if _, ok := <-subscription.Events; ok {
		t.Fatal("subscription remained open after buffer overflow")
	}
}

func TestLogHubCloseClosesSubscriptions(t *testing.T) {
	hub := NewLogHub()
	subscription := hub.Subscribe()

	hub.Close()

	select {
	case _, ok := <-subscription.Events:
		if ok {
			t.Fatal("subscription remained open after hub close")
		}
	case <-time.After(time.Second):
		t.Fatal("subscription did not close after hub close")
	}

	hub.Close()
	lateSubscription := hub.Subscribe()
	if _, ok := <-lateSubscription.Events; ok {
		t.Fatal("subscription created after hub close remained open")
	}
}
