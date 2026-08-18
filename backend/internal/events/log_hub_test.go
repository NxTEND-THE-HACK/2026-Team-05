package events

import (
	"testing"

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
