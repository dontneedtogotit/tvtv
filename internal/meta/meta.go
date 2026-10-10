package meta

import (
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// EnrichedStream is the v1 contract returned by the metadata service.
type EnrichedStream struct {
	StreamID  uuid.UUID `json:"streamId"`
	Title     string    `json:"title"`
	StartTime string    `json:"startTime"`
	Duration  int       `json:"duration"`
	DRMKeyID  *string   `json:"drmKeyId"`
}

// ErrNotFound is returned when a stream ID is unknown.
var ErrNotFound = errors.New("meta: stream not found")

// Service exposes Enrich(streamId UUID) -> EnrichedStream via gRPC v1.
type Service struct {
	repo StreamLookup
}

// StreamLookup is the persistence seam for metadata enrichment.
type StreamLookup interface {
	Get(uuid.UUID) (EnrichedStream, error)
}

// NewService constructs a metadata service.
func NewService(repo StreamLookup) *Service {
	return &Service{repo: repo}
}

// Enrich enriches a stream and rejects unknown IDs with NotFound.
func (s *Service) Enrich(id uuid.UUID) (EnrichedStream, error) {
	stream, err := s.repo.Get(id)
	if err != nil {
		return EnrichedStream{}, fmt.Errorf("meta: enrich: %w", ErrNotFound)
	}
	if stream.Title == "" || stream.StartTime == "" || stream.Duration == 0 {
		return EnrichedStream{}, fmt.Errorf("meta: enrich: %w", errors.New("missing mandatory fields"))
	}
	return stream, nil
}
