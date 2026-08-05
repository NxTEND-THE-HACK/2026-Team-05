/**
 * TEMP_BACKEND_DEMO
 * バックエンドAPIの結合確認用に作成した仮画面です。
 * 正式フロントへ置き換える際は docs/temporary-backend-demo-ui.md を参照してください。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Route } from "./+types/backend-demo";
import {
  executeAction,
  getApiBaseUrl,
  getSnapshot,
  saveBinding,
} from "~/services/backendApiClient";
import type {
  Action,
  ActionLogStatus,
  BackendSnapshot,
  Motion,
} from "~/types/backendApi";
import "./backend-demo.css";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Backend Demo Console" },
    {
      name: "description",
      content: "モーションとTuya家電操作を試すための仮フロント",
    },
  ];
}

type Draft = { actionId: string; cameraId: string };

const EMPTY_SNAPSHOT: BackendSnapshot = {
  cameras: [],
  motions: [],
  appliances: [],
  actions: [],
  bindings: [],
  logs: [],
};

function Icon({ name }: { name: "motion" | "plug" | "link" | "log" | "refresh" | "play" | "check" | "alert" }) {
  const paths = {
    motion: <><path d="M12 5.2a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4Z"/><path d="m9.8 8.2 2.2-1 2.2 1 2.3 3.5M12 7.2v5.2m0 0-3.2 5.8m3.2-5.8 3.4 5.8M7.4 9.7l2.4-1.5m6.8 1.5-2.4-1.5"/></>,
    plug: <><path d="M8 2v5m8-5v5M6 7h12v2a6 6 0 0 1-6 6v0a6 6 0 0 1-6-6V7Zm6 8v7"/></>,
    link: <><path d="M9.5 14.5 14.5 9"/><path d="M7.8 17.8 5.6 20a4 4 0 0 1-5.6-5.6l4-4A4 4 0 0 1 9.6 10M16.2 6.2 18.4 4A4 4 0 1 1 24 9.6l-4 4a4 4 0 0 1-5.6.4"/></>,
    log: <><path d="M5 3h14v18H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></>,
    refresh: <><path d="M20 6v5h-5"/><path d="M18.5 16a8 8 0 1 1 .7-8.5L20 11"/></>,
    play: <path d="m8 5 11 7-11 7V5Z"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    alert: <><path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3h.01"/></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function statusLabel(status: ActionLogStatus): string {
  return {
    SUCCESS: "成功",
    FAILED: "失敗",
    COOLING_DOWN: "待機中",
  }[status];
}

export default function BackendDemo() {
  const [data, setData] = useState<BackendSnapshot>(EMPTY_SNAPSHOT);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [savingMotion, setSavingMotion] = useState<string | null>(null);
  const [runningAction, setRunningAction] = useState<string | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    else setLoading(true);
    try {
      const snapshot = await getSnapshot();
      setData(snapshot);
      setDrafts(
        Object.fromEntries(
          snapshot.motions.map((motion) => {
            const binding = snapshot.bindings.find(
              (item) => item.motionId === motion.id,
            );
            return [
              motion.id,
              {
                actionId: binding?.actionId ?? "",
                cameraId: binding?.cameraId ?? "",
              },
            ];
          }),
        ),
      );
      setError(null);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "APIへの接続に失敗しました",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const applianceById = useMemo(
    () => new Map(data.appliances.map((item) => [item.id, item])),
    [data.appliances],
  );
  const actionById = useMemo(
    () => new Map(data.actions.map((item) => [item.id, item])),
    [data.actions],
  );

  const updateDraft = (motionId: string, patch: Partial<Draft>) => {
    setDrafts((current) => ({
      ...current,
      [motionId]: { ...current[motionId], ...patch },
    }));
  };

  const handleSave = async (motion: Motion) => {
    const draft = drafts[motion.id];
    if (!draft?.actionId) return;
    setSavingMotion(motion.id);
    setNotice(null);
    try {
      await saveBinding({
        motionId: motion.id,
        actionId: draft.actionId,
        ...(draft.cameraId ? { cameraId: draft.cameraId } : {}),
      });
      setNotice(`「${motion.name}」の操作を保存しました`);
      await load(true);
    } catch (cause) {
      setNotice(
        `保存失敗: ${cause instanceof Error ? cause.message : "不明なエラー"}`,
      );
    } finally {
      setSavingMotion(null);
    }
  };

  const handleExecute = async (action: Action) => {
    setRunningAction(action.id);
    setNotice(null);
    try {
      const result = await executeAction(action.id);
      setNotice(
        result.success
          ? `「${action.name}」を実行しました`
          : `実行失敗: ${result.message ?? "Tuya操作に失敗しました"}`,
      );
      await load(true);
    } catch (cause) {
      setNotice(
        `実行失敗: ${cause instanceof Error ? cause.message : "不明なエラー"}`,
      );
    } finally {
      setRunningAction(null);
    }
  };

  return (
    <main className="bd-page">
      <div className="bd-shell">
        <header className="bd-header">
          <div>
            <div className="bd-eyebrow"><span /> BACKEND DEMO CONSOLE</div>
            <h1>Motion <em>→</em> Home</h1>
            <p>認識した動きを、家電のアクションへ。バックエンドの今を試す仮画面です。</p>
          </div>
          <div className="bd-connection">
            <span className={`bd-dot ${error ? "is-error" : ""}`} />
            <div><b>{error ? "API offline" : "API connected"}</b><small>{getApiBaseUrl()}</small></div>
            <button type="button" onClick={() => void load(true)} disabled={refreshing} aria-label="再読み込み"><Icon name="refresh" /></button>
          </div>
        </header>

        {error && (
          <section className="bd-error" role="alert">
            <Icon name="alert" />
            <div><b>バックエンドに接続できません</b><p>{error}</p><code>cd backend &amp;&amp; TUYA_DRY_RUN=true go run ./cmd/server</code></div>
          </section>
        )}

        {notice && <div className="bd-toast"><Icon name={notice.startsWith("実行失敗") || notice.startsWith("保存失敗") ? "alert" : "check"} />{notice}<button type="button" onClick={() => setNotice(null)}>×</button></div>}

        <section className="bd-stats" aria-label="登録状況">
          <Stat icon="motion" value={data.motions.length} label="Motions" detail="認識できる動作" />
          <Stat icon="plug" value={data.appliances.length} label="Appliances" detail="登録されている家電" />
          <Stat icon="link" value={data.bindings.length} label="Bindings" detail="設定済みの紐付け" />
          <Stat icon="log" value={data.logs.length} label="Recent logs" detail="直近の操作履歴" />
        </section>

        {loading ? (
          <div className="bd-loading"><span /><p>バックエンドの状態を取得しています</p></div>
        ) : (
          <>
            <div className="bd-grid">
              <section className="bd-panel bd-mapping-panel">
                <PanelHeading number="01" title="モーションの紐付け" subtitle="動きを選び、実行する家電操作を設定します" />
                <div className="bd-motion-list">
                  {data.motions.map((motion) => {
                    const draft = drafts[motion.id] ?? { actionId: "", cameraId: "" };
                    const binding = data.bindings.find((item) => item.motionId === motion.id);
                    const selected = actionById.get(draft.actionId);
                    return (
                      <article className="bd-motion-card" key={motion.id}>
                        <div className="bd-motion-symbol"><Icon name="motion" /></div>
                        <div className="bd-motion-main">
                          <div className="bd-motion-title"><div><h3>{motion.name}</h3><code>{motion.code}</code></div><span className={binding ? "is-bound" : ""}>{binding ? "設定済み" : "未設定"}</span></div>
                          <p>{motion.description}</p>
                          <div className="bd-form-row">
                            <label><span>実行する操作</span><select value={draft.actionId} onChange={(event) => updateDraft(motion.id, { actionId: event.target.value })}><option value="">操作を選択</option>{data.actions.map((action) => <option key={action.id} value={action.id}>{action.name} · {applianceById.get(action.applianceId)?.name}</option>)}</select></label>
                            <label><span>カメラ（将来用・任意）</span><select value={draft.cameraId} onChange={(event) => updateDraft(motion.id, { cameraId: event.target.value })}><option value="">指定しない</option>{data.cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name} · {camera.location}</option>)}</select></label>
                          </div>
                          <div className="bd-motion-footer"><div>{selected ? <><span className={`bd-power ${selected.params.value ? "is-on" : "is-off"}`} />{selected.params.value ? "電源 ON" : "電源 OFF"}<small>{selected.params.deviceIdEnv ?? selected.params.deviceId ?? "Device未指定"}</small></> : "操作を選択してください"}</div><button type="button" onClick={() => void handleSave(motion)} disabled={!draft.actionId || savingMotion === motion.id}>{savingMotion === motion.id ? "保存中…" : "紐付けを保存"}</button></div>
                        </div>
                      </article>
                    );
                  })}
                  {data.motions.length === 0 && <Empty text="モーションが登録されていません" />}
                </div>
              </section>

              <aside className="bd-side">
                <section className="bd-panel">
                  <PanelHeading number="02" title="手動テスト" subtitle="Tuyaアクションを直接実行します" />
                  <div className="bd-action-list">
                    {data.actions.map((action) => (
                      <button className="bd-action" type="button" key={action.id} onClick={() => void handleExecute(action)} disabled={runningAction === action.id}>
                        <span className={`bd-action-icon ${action.params.value ? "is-on" : "is-off"}`}><Icon name="plug" /></span>
                        <span><b>{action.name}</b><small>{applianceById.get(action.applianceId)?.name} · {action.params.deviceIdEnv ?? "Direct ID"}</small></span>
                        <span className="bd-play">{runningAction === action.id ? <i /> : <Icon name="play" />}</span>
                      </button>
                    ))}
                  </div>
                  <p className="bd-hint">実機操作かDry-runかは、バックエンドの <code>TUYA_DRY_RUN</code> 設定に従います。</p>
                </section>
              </aside>
            </div>

            <section className="bd-panel bd-logs-panel">
              <PanelHeading number="03" title="操作ログ" subtitle="Python認識と手動テストの結果を確認できます" />
              <div className="bd-table-wrap">
                <table><thead><tr><th>状態</th><th>モーション</th><th>実行アクション</th><th>カメラ</th><th>検出時刻</th></tr></thead><tbody>{data.logs.map((log) => <tr key={log.id}><td><span className={`bd-status is-${log.status.toLowerCase()}`}>{statusLabel(log.status)}</span></td><td><b>{log.motionName ?? log.motionCode}</b><small>{log.motionCode}</small></td><td><b>{log.actionName ?? "—"}</b>{log.errorMessage && <small className="is-error-text">{log.errorMessage}</small>}</td><td>{log.cameraName ?? log.cameraId}</td><td>{formatDate(log.detectedAt)}</td></tr>)}</tbody></table>
                {data.logs.length === 0 && <Empty text="まだ操作ログはありません" />}
              </div>
            </section>
          </>
        )}

        <footer className="bd-footer"><span>PROTOTYPE UI</span><p>この画面はバックエンドAPIを試すための仮実装です。</p></footer>
      </div>
    </main>
  );
}

function Stat({ icon, value, label, detail }: { icon: "motion" | "plug" | "link" | "log"; value: number; label: string; detail: string }) {
  return <article className="bd-stat"><div className="bd-stat-icon"><Icon name={icon} /></div><div><strong>{value.toString().padStart(2, "0")}</strong><b>{label}</b><small>{detail}</small></div></article>;
}

function PanelHeading({ number, title, subtitle }: { number: string; title: string; subtitle: string }) {
  return <div className="bd-panel-heading"><span>{number}</span><div><h2>{title}</h2><p>{subtitle}</p></div></div>;
}

function Empty({ text }: { text: string }) {
  return <div className="bd-empty"><span>—</span>{text}</div>;
}
