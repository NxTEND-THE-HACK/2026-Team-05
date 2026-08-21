import { useEffect, useMemo, useState } from "react";
import {
  Button,
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
import { PlusOutlined } from "@ant-design/icons";
import { useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { useAppliances } from "~/hooks/useAppliances";
import { useBindings } from "~/hooks/useBindings";
import { useActions } from "~/hooks/useActions";
import { useMotions } from "~/hooks/useMotions";
import { useExecuteAction } from "~/hooks/useExecuteAction";
import { useApplianceState } from "~/hooks/useApplianceState";
import { useTestIR } from "~/hooks/useIRController";
import { queryKeys } from "~/hooks/queryKeys";
import { IRControllerStatus } from "~/components/ir/IRControllerStatus";
import { IRActionButtonGrid } from "~/components/ir/IRActionButtonGrid";
import { IRLearnActionModal } from "~/components/ir/IRLearnActionModal";
import { TuyaActionFormModal } from "~/components/action/TuyaActionFormModal";
import {
  groupActionsIntoRows,
  isRowToggleable,
  type ControlRow,
} from "~/lib/controlRows";
import {
  reconcileOptimisticState,
  resolveDisplayStateValue,
} from "~/lib/displayState";
import {
  isIRAction,
  isTuyaAction,
  type IRAction,
  type MotionBinding,
  type Motion,
  type Action,
} from "~/types/backendApi";

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
  const [learnModalOpen, setLearnModalOpen] = useState(false);
  const [tuyaActionModalOpen, setTuyaActionModalOpen] = useState(false);

  const loading =
    appliancesLoading || bindingsLoading || actionsLoading || motionsLoading;

  const appliance = useMemo(
    () => appliances.find((a) => a.id === deviceId),
    [appliances, deviceId],
  );

  const isIR = appliance?.controlProvider === "ESP32_IR";

  const deviceActions = useMemo(
    () => actions.filter((a) => a.applianceId === appliance?.id),
    [actions, appliance?.id],
  );

  const tuyaActions = useMemo(
    () => deviceActions.filter(isTuyaAction),
    [deviceActions],
  );

  const irActions = useMemo(
    () => deviceActions.filter(isIRAction),
    [deviceActions],
  );

  const controlRows = useMemo<ControlRow[]>(
    () => groupActionsIntoRows(tuyaActions),
    [tuyaActions],
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
  // 赤外線デバイスでは実機状態を取得できないため、Tuya のときだけ有効化する。
  const { data: applianceState, isLoading: applianceStateLoading, dataUpdatedAt } =
    useApplianceState(!isIR ? deviceId : undefined);

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
    const rowState = resolveStateForRow(row);
    return resolveDisplayStateValue({
      optimistic: optimisticState[row.key],
      rowState,
    });
  };

  // applianceState が更新 (=フェッチ完了) するたびに、楽観状態と実機状態が
  // 一致していれば楽観状態をクリアする。一致していない間は Tuya Cloud への
  // 反映遅延や物理操作が疑われるため、ユーザが押した結果を最優先で表示し続ける。
  useEffect(() => {
    if (dataUpdatedAt === 0) return;
    const actualValues: Record<string, boolean | undefined> = {};
    for (const row of controlRows) {
      const rowState = resolveStateForRow(row);
      actualValues[row.key] =
        rowState?.value !== null && rowState?.value !== undefined
          ? rowState.value
          : undefined;
    }
    setOptimisticState((prev) => reconcileOptimisticState(prev, actualValues));
  }, [dataUpdatedAt, controlRows, applianceState]);

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
    if (!isRowToggleable(row)) {
      message.warning(
        `${row.name} は ON/OFF 両方のアクションが揃っていないため操作できません`,
      );
      return;
    }
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
          <Descriptions.Item label="操作方式">
            {isIR ? (
              <Tag color="purple">赤外線 (ESP32_IR)</Tag>
            ) : (
              <Tag color="blue">Tuya</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="ID">{appliance.id}</Descriptions.Item>
        </Descriptions>
      </Card>

      {isIR ? (
        <IRManualControl
          applianceId={appliance.id}
          irActions={irActions}
          actionsLoading={actionsLoading}
          onLearn={() => setLearnModalOpen(true)}
        />
      ) : (
        <Card
          title="Manual Control"
          extra={
            <Space size="small">
              <Text type="secondary" style={{ fontSize: 12 }}>
                モーションを使わずに直接操作
              </Text>
              <Button
                type="primary"
                size="small"
                icon={<PlusOutlined />}
                onClick={() => setTuyaActionModalOpen(true)}
              >
                操作を追加
              </Button>
            </Space>
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
                "このデバイスに登録されたアクションがありません。「操作を追加」から作成してください。",
            }}
          />
        </Card>
      )}

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

      <IRLearnActionModal
        applianceId={appliance.id}
        open={learnModalOpen}
        onClose={() => setLearnModalOpen(false)}
      />
      <TuyaActionFormModal
        applianceId={appliance.id}
        open={tuyaActionModalOpen}
        onClose={() => setTuyaActionModalOpen(false)}
      />
    </Space>
  );
}

function IRManualControl({
  applianceId,
  irActions,
  actionsLoading,
  onLearn,
}: {
  applianceId: string;
  irActions: IRAction[];
  actionsLoading: boolean;
  onLearn: () => void;
}) {
  const testIR = useTestIR();
  const [testing, setTesting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    try {
      await testIR.mutateAsync(applianceId);
      message.success("赤外線LEDテスト信号を送信しました");
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "テスト信号の送信に失敗しました",
      );
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card
      title="Manual Control"
      extra={
        <Space size="small">
          <Text type="secondary" style={{ fontSize: 12 }}>
            登録済みの赤外線ボタン
          </Text>
          <Button size="small" loading={testing} onClick={handleTest}>
            LEDテスト
          </Button>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onLearn}>
            ボタンを登録
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <IRControllerStatus applianceId={applianceId} />
        <IRActionButtonGrid
          actions={irActions}
          loading={actionsLoading}
        />
      </Space>
    </Card>
  );
}
