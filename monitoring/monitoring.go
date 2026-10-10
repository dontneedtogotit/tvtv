package monitoring

import (
	"fmt"
	"log/slog"
	"net/http"
	"path/filepath"
	"sync/atomic"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	up = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "up",
		Help: "1 when all subsystems report healthy.",
	})
	healthLatency = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "healthz_latency_seconds",
		Help:    "Latency of health checks.",
		Buckets: prometheus.DefBuckets,
	})
)

var subsystemStatus atomic.Int32 // 1 = healthy, 0 = unhealthy

func init() {
	prometheus.MustRegister(up, healthLatency)
}

// LoadConfig imports a Prometheus config file; the path MUST be absolute.
func LoadConfig(path string) (string, error) {
	if !filepath.IsAbs(path) {
		return "", fmt.Errorf("monitoring: config path must be absolute, got %q", path)
	}
	content, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	return content, nil
}

// SetHealthy flips the up metric according to subsystem health.
func SetHealthy(healthy bool) {
	if healthy {
		subsystemStatus.Store(1)
	} else {
		subsystemStatus.Store(0)
	}
	up.Set(float64(subsystemStatus.Load()))
}

// Healthz is the /healthz handler.
func Healthz(logger *slog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		defer func() { healthLatency.Observe(time.Since(start).Seconds()) }()
		if subsystemStatus.Load() == 0 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	}
}

// Handler returns the Prometheus metrics handler.
func Handler() http.Handler {
	return promhttp.Handler()
}
