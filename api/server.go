package api

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/go-playground/validator/v10"
	"github.com/google/uuid"
)

// Error response shape per the OpenAPI spec.
type APIError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	TraceID string `json:"traceId,omitempty"`
}

// ErrorMapper maps internal error codes to public API error codes.
type ErrorMapper struct {
	logger *slog.Logger
}

func NewErrorMapper(logger *slog.Logger) *ErrorMapper {
	return &ErrorMapper{logger: logger}
}

// Map translates an internal error to an (HTTP status, APIError).
func (m *ErrorMapper) Map(err error) (int, APIError) {
	switch {
	case errors.Is(err, ErrInvalidUUID):
		return http.StatusBadRequest, APIError{Code: "InvalidUUID", Message: err.Error()}
	case errors.Is(err, ErrNotFound):
		return http.StatusNotFound, APIError{Code: "NotFound", Message: err.Error()}
	default:
		m.logger.Error("internal error", "error", err)
		return http.StatusInternalServerError, APIError{Code: "InternalError", Message: "internal error"}
	}
}

var (
	ErrInvalidUUID = errors.New("api: invalid UUID")
	ErrNotFound    = errors.New("api: not found")
)

// Stream is the API representation matching the OpenAPI schema.
type Stream struct {
	ID        uuid.UUID `json:"id"`
	Title     string    `json:"title"`
	StartTime string    `json:"startTime"`
	Duration  int       `json:"duration"`
	DRMKeyID  *string   `json:"drmKeyId"`
	Status    string    `json:"status"`
}

// StreamRepo is the persistence seam (defined in db package, redeclared here as a seam).
type StreamRepo interface {
	List(ctx context.Context, status string) ([]Stream, error)
	Get(ctx context.Context, id uuid.UUID) (Stream, error)
}

// BookmarkRepo is the persistence seam for bookmarks.
type BookmarkRepo interface {
	Add(ctx context.Context, streamID uuid.UUID) error
}

// Server hosts the public API layer with semantic versioning in the URL.
type Server struct {
	mux       *http.ServeMux
	validator *validator.Validate
	streams   StreamRepo
	bookmarks BookmarkRepo
	mapper    *ErrorMapper
	logger    *slog.Logger
}

// NewServer constructs the API server. configPath must be absolute.
func NewServer(streams StreamRepo, bookmarks BookmarkRepo, configPath string, logger *slog.Logger) (*Server, error) {
	if !filepath.IsAbs(configPath) {
		return nil, errors.New("api: config path must be absolute")
	}
	s := &Server{
		validator: validator.New(),
		streams:   streams,
		bookmarks: bookmarks,
		mapper:    NewErrorMapper(logger),
		logger:    logger,
	}
	s.routes()
	return s, nil
}

func (s *Server) routes() {
	s.mux = http.NewServeMux()
	// Semantic versioning in URL.
	s.mux.HandleFunc("/v1/streams", s.handleStreams)
	s.mux.HandleFunc("/v1/streams/", s.handleStream)
}

// ServeHTTP implements http.Handler.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.mux.ServeHTTP(w, r)
}

func (s *Server) handleStreams(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, APIError{Code: "MethodNotAllowed", Message: "method not allowed"})
		return
	}
	status := r.URL.Query().Get("status")
	streams, err := s.streams.List(r.Context(), status)
	if err != nil {
		statusCode, apiErr := s.mapper.Map(err)
		writeError(w, statusCode, apiErr)
		return
	}
	writeJSON(w, http.StatusOK, streams)
}

func (s *Server) handleStream(w http.ResponseWriter, r *http.Request) {
	// Parse path: /v1/streams/{id} or /v1/streams/{id}/bookmark
	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	// Expect: ["v1", "streams", "{id}"] or ["v1", "streams", "{id}", "bookmark"]
	if len(parts) < 3 {
		writeError(w, http.StatusBadRequest, APIError{Code: "BadRequest", Message: "invalid path"})
		return
	}
	idStr := parts[2]
	id, err := uuid.Parse(idStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, APIError{Code: "InvalidUUID", Message: "invalid UUID"})
		return
	}

	if len(parts) == 4 && parts[3] == "bookmark" {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, APIError{Code: "MethodNotAllowed", Message: "method not allowed"})
			return
		}
		if err := s.bookmarks.Add(r.Context(), id); err != nil {
			statusCode, apiErr := s.mapper.Map(err)
			writeError(w, statusCode, apiErr)
			return
		}
		w.WriteHeader(http.StatusCreated)
		return
	}

	if r.Method == http.MethodGet {
		stream, err := s.streams.Get(r.Context(), id)
		if err != nil {
			statusCode, apiErr := s.mapper.Map(err)
			writeError(w, statusCode, apiErr)
			return
		}
		writeJSON(w, http.StatusOK, stream)
		return
	}

	writeError(w, http.StatusMethodNotAllowed, APIError{Code: "MethodNotAllowed", Message: "method not allowed"})
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, apiErr APIError) {
	writeJSON(w, status, apiErr)
}
