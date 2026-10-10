// Package cmd provides the TVTV service entrypoint with graceful shutdown.
package cmd

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/dontneedtogotit/tvtv/api"
	"github.com/dontneedtogotit/tvtv/db"
	"github.com/dontneedtogotit/tvtv/internal/worker"
	"github.com/dontneedtogotit/tvtv/monitoring"
	"github.com/google/uuid"
)

// Config holds absolute-path configuration values.
type Config struct {
	APIAddr          string // ":8080"
	MetricsAddr      string // ":9090"
	RedisAddr        string // "127.0.0.1:6379"
	StreamConfigPath string // Must be absolute
	PrometheusPath   string // Must be absolute
	ShutdownTimeout  time.Duration
}

// Run starts the service and blocks until SIGTERM is received.
// Implements FR-06 (graceful shutdown within 30s).
func Run(ctx context.Context, cfg Config, logger *slog.Logger) error {
	// Validate absolute paths (Constraint: Absolute Paths Only).
	for _, p := range []string{cfg.StreamConfigPath, cfg.PrometheusPath} {
		if !filepath.IsAbs(p) {
			return fmt.Errorf("cmd: path must be absolute: %q", p)
		}
	}

	// Set health to healthy on startup.
	monitoring.SetHealthy(true)

	// Start worker (FR-02).
	w := worker.NewWorker(cfg.RedisAddr, "tvtv:pending", logger)
	workerCtx, workerCancel := context.WithCancel(ctx)
	workerErrCh := make(chan error, 1)
	go func() {
		workerErrCh <- w.Run(workerCtx)
	}()

	// Start API server (FR-04).
	apiServer := &http.Server{Addr: cfg.APIAddr, Handler: nil} // Handler wired in production
	metricsServer := &http.Server{Addr: cfg.MetricsAddr, Handler: monitoring.Handler()}

	go func() {
		logger.Info("api listening", "addr", cfg.APIAddr)
		if err := apiServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("api server error", "error", err)
		}
	}()
	go func() {
		logger.Info("metrics listening", "addr", cfg.MetricsAddr)
		if err := metricsServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("metrics server error", "error", err)
		}
	}()

	// Wait for SIGTERM/SIGINT (FR-06).
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
	sig := <-sigCh
	logger.Info("received signal, draining", "signal", sig.String())

	// Graceful shutdown: drain in-flight jobs, flush buffers, close sockets.
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
	defer shutdownCancel()

	if err := apiServer.Shutdown(shutdownCtx); err != nil {
		logger.Error("api shutdown error", "error", err)
	}
	if err := metricsServer.Shutdown(shutdownCtx); err != nil {
		logger.Error("metrics shutdown error", "error", err)
	}
	workerCancel()
	if err := <-workerErrCh; err != nil && !errors.Is(err, context.Canceled) {
		logger.Error("worker shutdown error", "error", err)
	}

	logger.Info("GracefulShutdownComplete")
	return nil
}

// StreamRepoStub is a stub repository for bootstrapping.
type StreamRepoStub struct{}

func (s *StreamRepoStub) List(ctx context.Context, status string) ([]api.Stream, error) {
	return []api.Stream{}, nil
}

func (s *StreamRepoStub) Get(ctx context.Context, id uuid.UUID) (api.Stream, error) {
	return api.Stream{}, db.ErrNotFound
}

func (s *StreamRepoStub) Add(ctx context.Context, streamID uuid.UUID) error {
	return nil
}
