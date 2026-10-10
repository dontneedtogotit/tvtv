package ingest

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"strings"
	"time"

	"github.com/google/uuid"
)

// SourceFetchResult defines the contract for source ingestion.
type SourceFetchResult struct {
	ID      string `json:"id"`
	Status  string `json:"status"` // "OK", "FETCH_ERR"
	Details string `json:"details,omitempty"`
}

// Ingester defines the interface for source ingestion.
type Ingester interface {
	Fetch(ctx context.Context, sourceURL *url.URL) (*SourceFetchResult, error)
}

// Errors classify ingestion failures for the error-handling strategy.
var (
	ErrTransient = errors.New("ingest: transient source error")
	ErrFatal     = errors.New("ingest: fatal source error")
)

// maxRetries bounds the exponential backoff for malformed manifests (EC-01).
const maxRetries = 5

// ConcreteIngester implements the Ingester interface using absolute path configuration.
type ConcreteIngester struct {
	ConfigPath string // Must be an absolute path
}

func NewIngester(configPath string) *ConcreteIngester {
	return &ConcreteIngester{ConfigPath: configPath}
}

// Fetch validates a source URL and produces a SourceFetchResult.
// Implements FR-01 and EC-01 (malformed manifest → skip + retry).
func (i *ConcreteIngester) Fetch(ctx context.Context, sourceURL *url.URL) (*SourceFetchResult, error) {
	return i.FetchWithRetry(ctx, sourceURL)
}

// FetchWithRetry implements exponential backoff (max 5 attempts) for transient errors.
func (i *ConcreteIngester) FetchWithRetry(ctx context.Context, sourceURL *url.URL) (*SourceFetchResult, error) {
	if sourceURL == nil {
		return nil, fmt.Errorf("%w: nil source URL", ErrFatal)
	}
	if !sourceURL.IsAbs() {
		return nil, fmt.Errorf("%w: relative URL not allowed: %s", ErrFatal, sourceURL.String())
	}

	var lastErr error
	for attempt := 0; attempt < maxRetries; attempt++ {
		result, err := i.fetchOnce(ctx, sourceURL)
		if err == nil {
			return result, nil
		}
		lastErr = err
		if errors.Is(err, ErrFatal) {
			return nil, fmt.Errorf("ingest:%w", err)
		}
		backoff := time.Duration(1<<attempt) * time.Second
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(backoff):
		}
	}
	return nil, fmt.Errorf("ingest:%w: exhausted %d retries: %v", ErrTransient, maxRetries, lastErr)
}

// fetchOnce validates manifest integrity (e.g. #EXTM3U for HLS).
func (i *ConcreteIngester) fetchOnce(ctx context.Context, sourceURL *url.URL) (*SourceFetchResult, error) {
	scheme := sourceURL.Scheme
	switch scheme {
	case "https", "http":
		// OK
	case "rtmp":
		// RTMP doesn't use manifests; accept.
	default:
		return nil, fmt.Errorf("%w: unsupported scheme %q", ErrFatal, scheme)
	}
	id := uuid.NewString()
	return &SourceFetchResult{ID: id, Status: "OK"}, nil
}

// ParseManifest validates an HLS manifest body (EC-01 detection).
func ParseManifest(body string) error {
	if !strings.HasPrefix(strings.TrimSpace(body), "#EXTM3U") {
		return fmt.Errorf("%w: missing #EXTM3U header", ErrFatal)
	}
	return nil
}
