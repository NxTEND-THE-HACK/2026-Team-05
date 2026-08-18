package events

import (
	"sync"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
)

const logSubscriberBuffer = 32

// LogHub distributes newly persisted logs to subscribers in this process.
type LogHub struct {
	mu          sync.Mutex
	nextID      uint64
	subscribers map[uint64]chan domain.ActionLog
}

type LogSubscription struct {
	Events       <-chan domain.ActionLog
	unsubscribed func()
}

func NewLogHub() *LogHub {
	return &LogHub{subscribers: make(map[uint64]chan domain.ActionLog)}
}

func (h *LogHub) Subscribe() LogSubscription {
	h.mu.Lock()
	defer h.mu.Unlock()

	if h.subscribers == nil {
		h.subscribers = make(map[uint64]chan domain.ActionLog)
	}
	h.nextID++
	id := h.nextID
	channel := make(chan domain.ActionLog, logSubscriberBuffer)
	h.subscribers[id] = channel

	var once sync.Once
	return LogSubscription{
		Events: channel,
		unsubscribed: func() {
			once.Do(func() {
				h.unsubscribe(id)
			})
		},
	}
}

func (s LogSubscription) Close() {
	if s.unsubscribed != nil {
		s.unsubscribed()
	}
}

// Publish never waits for a slow client. A full subscription is closed so the
// client reconnects and refreshes the authoritative log list.
func (h *LogHub) Publish(log domain.ActionLog) {
	h.mu.Lock()
	defer h.mu.Unlock()

	for id, channel := range h.subscribers {
		select {
		case channel <- log:
		default:
			delete(h.subscribers, id)
			close(channel)
		}
	}
}

func (h *LogHub) unsubscribe(id uint64) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if channel, ok := h.subscribers[id]; ok {
		delete(h.subscribers, id)
		close(channel)
	}
}
