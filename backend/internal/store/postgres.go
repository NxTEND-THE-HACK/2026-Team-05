package store

import (
	"context"
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"time"

	"github.com/NxTEND-THE-HACK/2026-Team-05/backend/internal/domain"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrations embed.FS

type Postgres struct {
	pool *pgxpool.Pool
}

func NewPostgres(ctx context.Context, databaseURL string) (*Postgres, error) {
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		return nil, fmt.Errorf("configure postgres: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("connect postgres: %w", err)
	}
	p := &Postgres{pool: pool}
	if err := p.migrate(ctx); err != nil {
		pool.Close()
		return nil, err
	}
	return p, nil
}

func (p *Postgres) migrate(ctx context.Context) error {
	if _, err := p.pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version text PRIMARY KEY,
			applied_at timestamptz NOT NULL DEFAULT now()
		)`); err != nil {
		return fmt.Errorf("create schema migrations table: %w", err)
	}
	entries, err := fs.ReadDir(migrations, "migrations")
	if err != nil {
		return fmt.Errorf("read migrations: %w", err)
	}
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		tx, err := p.pool.Begin(ctx)
		if err != nil {
			return fmt.Errorf("begin migration %s: %w", entry.Name(), err)
		}
		if _, err := tx.Exec(ctx, `LOCK TABLE schema_migrations IN EXCLUSIVE MODE`); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("lock migrations for %s: %w", entry.Name(), err)
		}
		var applied bool
		if err := tx.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = $1)`, entry.Name()).Scan(&applied); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("check migration %s: %w", entry.Name(), err)
		}
		if applied {
			if err := tx.Commit(ctx); err != nil {
				return fmt.Errorf("finish migration check %s: %w", entry.Name(), err)
			}
			continue
		}
		body, err := migrations.ReadFile("migrations/" + entry.Name())
		if err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("read migration %s: %w", entry.Name(), err)
		}
		if _, err := tx.Exec(ctx, string(body)); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("apply migration %s: %w", entry.Name(), err)
		}
		if _, err := tx.Exec(ctx, `INSERT INTO schema_migrations (version) VALUES ($1)`, entry.Name()); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("record migration %s: %w", entry.Name(), err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", entry.Name(), err)
		}
	}
	return nil
}

func (p *Postgres) Health(ctx context.Context) error { return p.pool.Ping(ctx) }
func (p *Postgres) Close()                           { p.pool.Close() }

func (p *Postgres) ListCameras(ctx context.Context) ([]domain.Camera, error) {
	rows, err := p.pool.Query(ctx, `SELECT id, name, stream_url, location, is_enabled, created_at FROM cameras ORDER BY created_at, id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []domain.Camera{}
	for rows.Next() {
		var item domain.Camera
		if err := rows.Scan(&item.ID, &item.Name, &item.StreamURL, &item.Location, &item.IsEnabled, &item.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (p *Postgres) ListMotions(ctx context.Context) ([]domain.Motion, error) {
	rows, err := p.pool.Query(ctx, `SELECT id, code, name, description FROM motions ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []domain.Motion{}
	for rows.Next() {
		var item domain.Motion
		if err := rows.Scan(&item.ID, &item.Code, &item.Name, &item.Description); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (p *Postgres) ListAppliances(ctx context.Context) ([]domain.Appliance, error) {
	rows, err := p.pool.Query(ctx, `SELECT id, name, category, control_provider, controller_id, created_at FROM appliances ORDER BY created_at, id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []domain.Appliance{}
	for rows.Next() {
		var item domain.Appliance
		if err := rows.Scan(&item.ID, &item.Name, &item.Category, &item.ControlProvider, &item.ControllerID, &item.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (p *Postgres) ListActions(ctx context.Context, applianceID string) ([]domain.Action, error) {
	query := `SELECT id, appliance_id, name, provider_type, params FROM appliance_actions`
	args := []any{}
	if applianceID != "" {
		query += ` WHERE appliance_id = $1`
		args = append(args, applianceID)
	}
	query += ` ORDER BY id`
	rows, err := p.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []domain.Action{}
	for rows.Next() {
		var item domain.Action
		if err := rows.Scan(&item.ID, &item.ApplianceID, &item.Name, &item.ProviderType, &item.Params); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (p *Postgres) ListBindings(ctx context.Context) ([]domain.MotionBinding, error) {
	rows, err := p.pool.Query(ctx, `SELECT id, COALESCE(camera_id, ''), motion_id, action_id, is_enabled, created_at FROM motion_bindings ORDER BY created_at, id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []domain.MotionBinding{}
	for rows.Next() {
		var item domain.MotionBinding
		if err := rows.Scan(&item.ID, &item.CameraID, &item.MotionID, &item.ActionID, &item.IsEnabled, &item.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (p *Postgres) ListLogs(ctx context.Context, limit int) ([]domain.ActionLog, error) {
	rows, err := p.pool.Query(ctx, `
		SELECT id, event_id, camera_id, camera_name, motion_code, motion_name,
		       COALESCE(action_id, ''), action_name, status, error_message, detected_at
		FROM action_logs ORDER BY created_at DESC LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []domain.ActionLog{}
	for rows.Next() {
		var item domain.ActionLog
		if err := rows.Scan(&item.ID, &item.EventID, &item.CameraID, &item.CameraName, &item.MotionCode, &item.MotionName, &item.ActionID, &item.ActionName, &item.Status, &item.ErrorMessage, &item.DetectedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (p *Postgres) CreateAppliance(ctx context.Context, input domain.CreateApplianceInput) (domain.Appliance, error) {
	if input.ControlProvider == "" {
		input.ControlProvider = domain.ProviderTuya
	}
	id, err := domain.NewID("appliance")
	if err != nil {
		return domain.Appliance{}, err
	}
	item := domain.Appliance{
		ID:              id,
		Name:            input.Name,
		Category:        input.Category,
		ControlProvider: input.ControlProvider,
		ControllerID:    input.ControllerID,
		CreatedAt:       time.Now().UTC(),
	}
	_, err = p.pool.Exec(ctx, `
		INSERT INTO appliances (id, name, category, control_provider, controller_id, created_at)
		VALUES ($1, $2, $3, $4, $5, $6)`,
		item.ID, item.Name, item.Category, item.ControlProvider, item.ControllerID, item.CreatedAt)
	return item, mapPostgresError(err)
}

func (p *Postgres) CreateAction(ctx context.Context, input domain.CreateActionInput) (domain.Action, error) {
	id, err := domain.NewID("action")
	if err != nil {
		return domain.Action{}, err
	}
	item := domain.Action{ID: id, ApplianceID: input.ApplianceID, Name: input.Name, ProviderType: input.ProviderType, Params: input.Params}
	_, err = p.pool.Exec(ctx, `INSERT INTO appliance_actions (id, appliance_id, name, provider_type, params) VALUES ($1, $2, $3, $4, $5)`, item.ID, item.ApplianceID, item.Name, item.ProviderType, item.Params)
	return item, mapPostgresError(err)
}

func (p *Postgres) CreateBinding(ctx context.Context, input domain.CreateBindingInput) (domain.MotionBinding, error) {
	id, err := domain.NewID("binding")
	if err != nil {
		return domain.MotionBinding{}, err
	}
	item := domain.MotionBinding{ID: id, CameraID: input.CameraID, MotionID: input.MotionID, ActionID: input.ActionID, IsEnabled: true, CreatedAt: time.Now().UTC()}
	err = p.pool.QueryRow(ctx, `
		INSERT INTO motion_bindings (id, camera_id, motion_id, action_id, is_enabled, created_at)
		VALUES ($1, NULLIF($2, ''), $3, $4, true, $5)
		ON CONFLICT (motion_id) DO UPDATE
		SET camera_id = EXCLUDED.camera_id, action_id = EXCLUDED.action_id, is_enabled = true, last_executed_at = NULL
		RETURNING id, COALESCE(camera_id, ''), created_at`, item.ID, item.CameraID, item.MotionID, item.ActionID, item.CreatedAt).Scan(&item.ID, &item.CameraID, &item.CreatedAt)
	return item, mapPostgresError(err)
}

func (p *Postgres) DeleteAction(ctx context.Context, id string) error {
	tag, err := p.pool.Exec(ctx, `DELETE FROM appliance_actions WHERE id = $1`, id)
	if err != nil {
		return mapPostgresError(err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (p *Postgres) DeleteBinding(ctx context.Context, id string) error {
	tag, err := p.pool.Exec(ctx, `DELETE FROM motion_bindings WHERE id = $1`, id)
	if err != nil {
		return mapPostgresError(err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (p *Postgres) ActionByID(ctx context.Context, id string) (domain.Action, error) {
	var item domain.Action
	err := p.pool.QueryRow(ctx, `SELECT id, appliance_id, name, provider_type, params FROM appliance_actions WHERE id = $1`, id).Scan(&item.ID, &item.ApplianceID, &item.Name, &item.ProviderType, &item.Params)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Action{}, ErrNotFound
	}
	return item, err
}

func (p *Postgres) ApplianceByID(ctx context.Context, id string) (domain.Appliance, error) {
	var item domain.Appliance
	err := p.pool.QueryRow(ctx, `
		SELECT id, name, category, control_provider, controller_id, created_at
		FROM appliances WHERE id = $1`, id).Scan(
		&item.ID, &item.Name, &item.Category, &item.ControlProvider, &item.ControllerID, &item.CreatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Appliance{}, ErrNotFound
	}
	return item, err
}

func (p *Postgres) ClaimDetection(ctx context.Context, event domain.DetectionEvent, cooldown time.Duration, now time.Time) (domain.DetectionClaim, error) {
	tx, err := p.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.ReadCommitted})
	if err != nil {
		return domain.DetectionClaim{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	tag, err := tx.Exec(ctx, `INSERT INTO processed_events (event_id, received_at) VALUES ($1, $2) ON CONFLICT DO NOTHING`, event.EventID, now)
	if err != nil {
		return domain.DetectionClaim{}, err
	}
	if tag.RowsAffected() == 0 {
		return domain.DetectionClaim{Duplicate: true}, tx.Commit(ctx)
	}

	var cameraName string
	var enabled bool
	if err := tx.QueryRow(ctx, `SELECT name, is_enabled FROM cameras WHERE id = $1`, event.CameraID).Scan(&cameraName, &enabled); err != nil || !enabled {
		if err != nil && !errors.Is(err, pgx.ErrNoRows) {
			return domain.DetectionClaim{}, err
		}
		return p.commitRejected(ctx, tx, event, "camera is not registered or enabled")
	}
	var motionID, motionName string
	if err := tx.QueryRow(ctx, `SELECT id, name FROM motions WHERE code = $1`, event.MotionCode).Scan(&motionID, &motionName); err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return domain.DetectionClaim{}, err
		}
		return p.commitRejected(ctx, tx, event, "motion is not registered")
	}

	var bindingID string
	var lastExecutedAt *time.Time
	var action domain.Action
	err = tx.QueryRow(ctx, `
		SELECT b.id, b.last_executed_at, a.id, a.appliance_id, a.name, a.provider_type, a.params
		FROM motion_bindings b
		JOIN appliance_actions a ON a.id = b.action_id
		WHERE b.motion_id = $1 AND b.is_enabled = true
		FOR UPDATE OF b`, motionID).Scan(
		&bindingID, &lastExecutedAt, &action.ID, &action.ApplianceID, &action.Name, &action.ProviderType, &action.Params,
	)
	if err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return domain.DetectionClaim{}, err
		}
		input := domain.ActionLog{EventID: event.EventID, CameraID: event.CameraID, CameraName: cameraName, MotionCode: event.MotionCode, MotionName: motionName, Status: domain.LogFailed, ErrorMessage: "motion binding was not found", DetectedAt: event.DetectedAt}
		log, err := appendLogTx(ctx, tx, input)
		if err != nil {
			return domain.DetectionClaim{}, err
		}
		return domain.DetectionClaim{Log: &log}, tx.Commit(ctx)
	}

	baseLog := domain.ActionLog{EventID: event.EventID, CameraID: event.CameraID, CameraName: cameraName, MotionCode: event.MotionCode, MotionName: motionName, ActionID: action.ID, ActionName: action.Name, DetectedAt: event.DetectedAt}
	if lastExecutedAt != nil && now.Before(lastExecutedAt.Add(cooldown)) {
		baseLog.Status = domain.LogCoolingDown
		log, err := appendLogTx(ctx, tx, baseLog)
		if err != nil {
			return domain.DetectionClaim{}, err
		}
		return domain.DetectionClaim{Log: &log}, tx.Commit(ctx)
	}
	if _, err := tx.Exec(ctx, `UPDATE motion_bindings SET last_executed_at = $2 WHERE id = $1`, bindingID, now); err != nil {
		return domain.DetectionClaim{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.DetectionClaim{}, err
	}
	return domain.DetectionClaim{Action: &action, Log: &baseLog}, nil
}

func (p *Postgres) commitRejected(ctx context.Context, tx pgx.Tx, event domain.DetectionEvent, message string) (domain.DetectionClaim, error) {
	input := domain.ActionLog{EventID: event.EventID, CameraID: event.CameraID, MotionCode: event.MotionCode, Status: domain.LogFailed, ErrorMessage: message, DetectedAt: event.DetectedAt}
	log, err := appendLogTx(ctx, tx, input)
	if err != nil {
		return domain.DetectionClaim{}, err
	}
	return domain.DetectionClaim{Log: &log}, tx.Commit(ctx)
}

func (p *Postgres) AppendLog(ctx context.Context, input domain.ActionLog) (domain.ActionLog, error) {
	return appendLogTx(ctx, p.pool, input)
}

type queryExecer interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func appendLogTx(ctx context.Context, db queryExecer, input domain.ActionLog) (domain.ActionLog, error) {
	id, err := domain.NewID("log")
	if err != nil {
		return domain.ActionLog{}, err
	}
	input.ID = id
	err = db.QueryRow(ctx, `
		INSERT INTO action_logs (id, event_id, camera_id, camera_name, motion_code, motion_name, action_id, action_name, status, error_message, detected_at)
		VALUES ($1, $2, $3, $4, $5, $6, NULLIF($7, ''), $8, $9, $10, $11)
		RETURNING id`, input.ID, input.EventID, input.CameraID, input.CameraName, input.MotionCode, input.MotionName, input.ActionID, input.ActionName, input.Status, input.ErrorMessage, input.DetectedAt).Scan(&input.ID)
	return input, err
}

func mapPostgresError(err error) error {
	if err == nil {
		return nil
	}
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) {
		switch pgErr.Code {
		case "23503":
			return fmt.Errorf("referenced resource: %w", ErrNotFound)
		case "23505":
			return ErrConflict
		}
	}
	return err
}
