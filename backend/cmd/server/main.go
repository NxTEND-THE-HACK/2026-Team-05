package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/api"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/config"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/executor"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/service"
	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/store"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if err := run(logger); err != nil {
		logger.Error("server stopped", "error", err)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	var repository store.Store
	if cfg.DatabaseURL == "" {
		repository = store.NewMemory(store.DefaultSeed(time.Now()))
		logger.Warn("DATABASE_URL is empty; using non-persistent in-memory storage")
	} else {
		repository, err = store.NewPostgres(ctx, cfg.DatabaseURL)
		if err != nil {
			return err
		}
		logger.Info("PostgreSQL storage connected")
	}
	defer repository.Close()

	tuyaExecutor, err := executor.NewTuya(cfg.Tuya, logger)
	if err != nil {
		return err
	}
	registry := executor.NewRegistry(tuyaExecutor)
	appService := service.New(repository, registry, cfg.Cooldown)
	e := api.New(repository, appService, logger, cfg.AllowedOrigins)

	errCh := make(chan error, 1)
	go func() {
		logger.Info("HTTP server started", "port", cfg.Port, "tuya_dry_run", cfg.Tuya.DryRun)
		if err := e.Start(":" + cfg.Port); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
	}()

	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
	select {
	case err := <-errCh:
		return err
	case <-signals:
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()
		return e.Shutdown(shutdownCtx)
	}
}
