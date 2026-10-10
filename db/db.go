package db

import (
	"context"
	"errors"

	"github.com/google/uuid"
)

// ErrNotFound is returned when a stream does not exist.
var ErrNotFound = errors.New("db: stream not found")

// StreamRepo abstracts stream persistence.
type StreamRepo interface {
	List(ctx context.Context, status string) ([]Stream, error)
	Get(ctx context.Context, id uuid.UUID) (Stream, error)
}

// BookmarkRepo abstracts bookmark persistence.
type BookmarkRepo interface {
	Add(ctx context.Context, streamID uuid.UUID) error
}

// Stream is the persisted stream record.
type Stream struct {
	ID        uuid.UUID `json:"id"`
	Title     string    `json:"title"`
	StartTime string    `json:"startTime"`
	Duration  int       `json:"duration"`
	DRMKeyID  *string   `json:"drmKeyId"`
	Status    string    `json:"status"`
}
