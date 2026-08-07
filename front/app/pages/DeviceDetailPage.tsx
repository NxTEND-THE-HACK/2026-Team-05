import { useEffect, useMemo, useState } from "react";
import {
  Card,
  Descriptions,
  Result,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { useAppliances } from "~/hooks/useAppliances";
import { useBindings } from "~/hooks/useBindings";
import { useActions } from "~/hooks/useActions";
import { useMotions } from "~/hooks/useMotions";
import { useExecuteAction } from "~/hooks/useExecuteAction";
import { useApplianceState } from "~/hooks/useApplianceState";
import { queryKeys } from "~/hooks/queryKeys";
import {
  groupActionsIntoRows,
  isRowToggleable,
  type ControlRow,
} from "~/lib/controlRows";
import type { MotionBinding, Motion, Action } from "~/types/backendApi";

const { Title, Text } = Typography;

interface BindingRow {
  key: string;
  binding: MotionBinding;
  motion?: Motion;
  action?: Action;
}

const bindingColumns: ColumnsType<BindingRow> = [
  {
    title: "Motion",
    key: "motion",
    render: (_: unknown, row: BindingRow) =>
      row.motion?.name ?? row.binding.motionId,
  },
  {
    title: "Action",
    key: "action",
    render: (_: unknown, row: BindingRow) =>
      row.action?.name ?? row.binding.actionId,
  },
  {
    title: "Enabled",
    key: "enabled",
    width: 120,
    render: (_: unknown, row: BindingRow) => (
      <Tag color={row.binding.isEnabled ? "success" : "default"}>
        {row.binding.isEnabled ? "有効" : "無効"}
      </Tag>
    ),
  },
];

export function DeviceDetailPage() {
  const { deviceId } = useParams<{ deviceId: string }>();
  const { data: appliances = [], isLoading: appliancesLoading } =
    useAppliances();
  const { data: bindings = [], isLoading: bindingsLoading } = useBindings();
  const { data: actions = [], isLoading: actionsLoading } =
    useActions(deviceId);
  const { data: motions = [], isLoading: motionsLoading } = useMotions();
  const executeAction = useExecuteAction();
  const queryClient = useQueryClient();
  const [executingId, setExecutingId] = useState<string | null>(null);

  const loading =
    appliancesLoading || bindingsLoading || actionsLoading || motionsLoading;

  const appliance = useMemo(
    () => appliances.find((a) => a.id === deviceId),
    [appliances, deviceId],
  );

  const deviceActions = useMemo(
    () => actions.filter((a) => a.applianceId === appliance?.id),
    [actions, appliance?.id],
  );

  const controlRows = useMemo<ControlRow[]>(
    () => groupActionsIntoRows(deviceActions),
    [deviceActions],
  );

  // 行ごとに「直前に実行した結果が on かどうか」を覚えておく楽観的状態。
  // 未実行時は undefined とし、ON 側の Action が存在すれば on 扱い (ON アクションの
  // デフォルト起動起点) とする。値が存在しない場合は OFF として扱う。
  const [optimisticState, setOptimisticState] = useState<Record<string, boolean>>({});

  // バックエンドから実機状態を取得 (Tuya 経由 / dry-run 時は null)。
  // 表示は次の優先順:
  //   1) optimisticState (直前のトグル操作の即時反映)
  //   2) applianceState.value (バックエンドが返した実機の値)
  //   3) "unknown" (値不明)
  // optimisticState は applianceState が更新されるたびにクリアし、Tuya 側の
  // 物理操作やポーリング結果が常に最優先で反映されるようにする。
  const { data: applianceState, isLoading: applianceStateLoading, dataUpdatedAt } =
    useApplianceState(deviceId);

  const resolveStateForRow = (row: ControlRow) => {
    if (!applianceState) return undefined;
    // 新しいレスポンスは switchCode ごとの states を優先する。
    // states がない旧レスポンスにも対応するため、配列が空の場合だけ
    // 従来のトップレベル状態へフォールバックする。
    if (applianceState.states?.length) {
      const switchCode =
        row.onAction?.params.switchCode?.trim() ||
        row.offAction?.params.switchCode?.trim() ||
        "switch";
      return applianceState.states.find(
        (item) => item.switchCode === switchCode,
      );
    }
    return applianceState;
  };

  const resolveDisplayState = (row: ControlRow): boolean | "unknown" => {
    if (optimisticState[row.key] !== undefined) return optimisticState[row.key];
    const rowState = resolveStateForRow(row);
    if (rowState?.value !== null && rowState?.value !== undefined) {
      return rowState.value;
    }
    return "unknown";
  };

  // applianceState が更新 (=フェッチ完了) するたびに楽観状態をクリアして、
  // ポーリング結果や invalidate 後の最新値を UI へ反映する。
  useEffect(() => {
    if (dataUpdatedAt === 0) return;
    setOptimisticState({});
  }, [dataUpdatedAt]);

  const bindingRows: BindingRow[] = useMemo(() => {
    if (!appliance) return [];
    const rows: BindingRow[] = [];
    for (const b of bindings) {
      const action = actions.find((a) => a.id === b.actionId);
      if (!action || action.applianceId !== appliance.id) continue;
      rows.push({
        key: b.id,
        binding: b,
        motion: motions.find((m) => m.id === b.motionId),
        action,
      });
    }
    return rows;
  }, [appliance, bindings, actions, motions]);

  const handleToggle = async (row: ControlRow, next: boolean) => {
    // 両方向の Action が揃っていない行はトグル不可。UI 側でも disabled にしているが、
    // 念のためここでも防御する。
    if (!isRowToggleable(row)) {
      message.warning(
        `${row.name} は ON/OFF 両方のアクションが揃っていないため操作できません`,
      );
      return;
    }
    // next と一致する方向の Action を厳密に選ぶ。存在しなければエラー。
    const target = next ? row.onAction : row.offAction;
    if (!target) {
      message.error(`${row.name} の ${next ? "ON" : "OFF"} アクションが見つかりません`);
      return;
    }
    setExecutingId(target.id);
    try {
      const result = await executeAction.mutateAsync(target.id);
      if (result.success) {
        setOptimisticState((prev) => ({ ...prev, [row.key]: next }));
        // バックエンド側の最新状態を即時取り直す。成功時の偽陽性や
        // Tuya 側の遅延反映もここで吸収する。invalidate 完了時に useEffect が
        // optimisticState をクリアするため、ポーリングや物理操作にも追従する。
        if (deviceId) {
          void queryClient.invalidateQueries({
            queryKey: queryKeys.applianceState(deviceId),
          });
        }
        message.success(
          `「${row.name}」を${next ? "ON" : "OFF"}にしました`,
        );
      } else {
        message.error(
          result.message
            ? `実行失敗: ${result.message}`
            : `「${row.name}」の実行に失敗しました`,
        );
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "実行に失敗しました";
      message.error(msg);
    } finally {
      setExecutingId(null);
    }
  };

  const actionColumns: ColumnsType<ControlRow> = [
    {
      title: "Appliance",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "Status",
      key: "status",
      width: 120,
      render: (_: unknown, row: ControlRow) => {
        const display = resolveDisplayState(row);
        const rowState = resolveStateForRow(row);
        if (display === "unknown") return <Tag>不明</Tag>;
        const source = rowState?.source;
        const tip = applianceStateLoading
          ? "実機状態を取得中"
          : rowState?.error
            ? rowState.error
          : source === "dry-run"
            ? "dry-run モード: 実機状態は取得できません"
            : source === "tuya"
              ? `最終取得: ${applianceState?.fetchedAt ?? "?"}`
              : "バックエンドから状態を取得できませんでした";
        return (
          <Tooltip title={tip}>
            <Tag color={display ? "success" : "default"}>
              {display ? "ON" : "OFF"}
            </Tag>
          </Tooltip>
        );
      },
    },
    {
      title: "Control",
      key: "control",
      width: 140,
      render: (_: unknown, row: ControlRow) => {
        const display = resolveDisplayState(row);
        // 不明状態 (value=null / 未取得) は checked を false に固定して、
        // 見た目上 ON と OFF のどちらでもない状態を作る。トグル操作で
        // ON へ倒すと ON Action が走り、OFF Action は未実行のため状態は遷移する。
        const checked = display === true;
        const toggleable = isRowToggleable(row);
        const isLoading =
          executingId !== null &&
          (executingId === row.onAction?.id || executingId === row.offAction?.id);
        const isDisabled = !toggleable || (executingId !== null && !isLoading);
        return (
          <Tooltip
            title={
              toggleable
                ? undefined
                : "ON/OFF 両方のアクションが揃っていないため操作できません"
            }
          >
            <Switch
              checked={checked}
              disabled={isDisabled}
              loading={isLoading}
              checkedChildren="ON"
              unCheckedChildren={display === "unknown" ? "?" : "OFF"}
              onChange={(checked) => handleToggle(row, checked)}
            />
          </Tooltip>
        );
      },
    },
  ];

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spin />
      </div>
    );
  }

  if (!appliance) {
    return (
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <BackToDashboard />
        <Result
          status="404"
          title="Device Not Found"
          subTitle={`デバイス ID: ${deviceId ?? "(unknown)"} は見つかりません`}
        />
      </Space>
    );
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <BackToDashboard />
      <Title level={3} style={{ margin: 0 }}>
        {appliance.name}
      </Title>
      <Card>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="Name">{appliance.name}</Descriptions.Item>
          <Descriptions.Item label="Category">
            {appliance.category}
          </Descriptions.Item>
          <Descriptions.Item label="Status">
            {(() => {
              const row = controlRows[0];
              if (!row) return <Tag>不明</Tag>;
              const display = resolveDisplayState(row);
              const rowState = resolveStateForRow(row);
              if (display === "unknown") return <Tag>不明</Tag>;
              const tip = rowState?.source === "dry-run"
                ? "dry-run モード"
                : rowState?.source === "tuya"
                  ? `最終取得: ${applianceState?.fetchedAt ?? "?"}`
                  : rowState?.error ?? "実機状態";
              return (
                <Tooltip title={tip}>
                  <Tag color={display ? "success" : "default"}>
                    {display ? "ON" : "OFF"}
                  </Tag>
                </Tooltip>
              );
            })()}
          </Descriptions.Item>
          <Descriptions.Item label="ID">{appliance.id}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title="Manual Control"
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            モーションを使わずに直接操作
          </Text>
        }
      >
        <Table
          columns={actionColumns}
          dataSource={controlRows}
          rowKey="key"
          pagination={false}
          size="middle"
          locale={{
            emptyText:
              "このデバイスに登録されたアクションがありません。アクション作成後に手動操作できます。",
          }}
        />
      </Card>

      <Card title="Bound Motions">
        <Table
          columns={bindingColumns}
          dataSource={bindingRows}
          rowKey="key"
          pagination={false}
          size="middle"
          locale={{
            emptyText: "このデバイスにバインドされたモーションはありません",
          }}
        />
      </Card>
    </Space>
  );
}
