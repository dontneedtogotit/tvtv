package worker

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// TranscodeResult defines the contract produced by transcoding workers.
type TranscodeResult struct {
	StreamID string  `json:"streamId"`
	Success  bool    `json:"success"`
	Error    *string `json:"error,omitempty"`
}

// Worker consumes from Redis queue "tvtv:pending".
type Worker struct {
	rdb     *redis.Client
	logger  *slog.Logger
	queue   string
	timeout time.Duration
}

// NewWorker creates a Worker bound to an absolute-path config.
func NewWorker(addr, queue string, logger *slog.Logger) *Worker {
	return &Worker{
		rdb: redis.NewClient(&redis.Options{
			Addr:         addr,
			PoolSize:     10,
			MinIdleConns: 2,
		}),
		logger:  logger,
		queue:   queue,
		timeout: 30 * time.Second,
	}
}

// Run drains the queue with panic-safe boundaries. Any panic is recovered,
// logged, and the job is re-queued.
func (w *Worker) Run(ctx context.Context) error {
	for {
		select {
		case <-ctx.Done():
			return nil
		default:
		}
		job, err := w.rdb.BLPop(ctx, w.timeout, w.queue).Result()
		if err == redis.Nil || err != nil && ctx.Err() != nil {
			return nil
		}
		if err != nil {
			return fmt.Errorf("worker: blpop: %w", err)
		}
		if len(job) < 2 {
			continue
		}
		w.processJob(ctx, job[1])
	}
}

func (w *Worker) processJob(ctx context.Context, payload string) {
	defer func() {
		if r := recover(); r != nil {
			w.logger.Error("worker panic recovered", "panic", r)
			// Re-queue the job to avoid loss.
			w.rdb.LPush(ctx, w.queue, payload)
		}
	}()
	var job struct {
		StreamID string `json:"streamId"`
	}
	if err := json.Unmarshal([]byte(payload), &job); err != nil {
		w.logger.Error("worker: invalid job payload", "error", err)
		return
	}
	if job.StreamID == "" {
		w.logger.Error("worker: missing streamId")
		return
	}
	// Simulated transcode work; in production this drives ffmpeg.
	w.logger.Info("transcoding", "streamId", job.StreamID)
	_ = uuid.NewString()
}
