import { useMemo, useState } from "react";
import {
  Card,
  Descriptions,
  Result,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useParams } from "react-router";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { useAppliances } from "~/hooks/useAppliances";
import { useBindings } from "~/hooks/useBindings";
import { useActions } from "~/hooks/useActions";
import { useMotions } from "~/hooks/useMotions";
import { useExecuteAction } from "~/hooks/useExecuteAction";
import type { MotionBinding, Motion, Action } from "~/types/backendApi";

const { Title, Text } = Typography;

interface BindingRow {
  key: string;
  binding: MotionBinding;
  motion?: Motion;
  action?: Action;
}

interface ControlRow {
  key: string;
  name: string;
  onAction?: Action;
  offAction?: Action;
}

/**
 * 1つの appliance に紐づく Action 群を、value=true / value=false のペアに集約する。
 * 同じ appliance 内に on/off 両方の Action がある場合のみトグル行を生成し、
 * 片方しか存在しない Action は対応する側だけを持った単一行として扱う。
 */
function groupActionsIntoRows(actions: Action[]): ControlRow[] {
  const groups = new Map<string, ControlRow>();
  for (const a of actions) {
    const row = groups.get(a.applianceId) ?? {
      key: a.applianceId,
      name: a.name.replace(/\s*(ON|OFF|オン|オフ)\s*$/i, "").trim() || a.name,
    };
    if (a.params.value === true) row.onAction = a;
    else if (a.params.value === false) row.offAction = a;
    else row.onAction = a; // value が無いものはとりあえず on 側に振り分けて単発実行可能にする
    groups.set(a.applianceId, row);
  }
  return Array.from(groups.values());
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
    // next=true → ON 側の Action を実行、next=false → OFF 側の Action を実行。
    // 片側しか存在しない場合は存在する方を実行する。
    const target =
      next ? row.onAction ?? row.offAction : row.offAction ?? row.onAction;
    if (!target) {
      message.error(`${row.name} に実行可能なアクションがありません`);
      return;
    }
    setExecutingId(target.id);
    try {
      const result = await executeAction.mutateAsync(target.id);
      if (result.success) {
        setOptimisticState((prev) => ({ ...prev, [row.key]: next }));
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
        const isOn = optimisticState[row.key] ?? row.onAction !== undefined;
        return (
          <Tag color={isOn ? "success" : "default"}>
            {isOn ? "ON" : "OFF"}
          </Tag>
        );
      },
    },
    {
      title: "Control",
      key: "control",
      width: 140,
      render: (_: unknown, row: ControlRow) => {
        const isOn = optimisticState[row.key] ?? row.onAction !== undefined;
        const isLoading =
          executingId !== null &&
          (executingId === row.onAction?.id || executingId === row.offAction?.id);
        const isDisabled =
          !row.onAction && !row.offAction
            ? true
            : executingId !== null && !isLoading;
        return (
          <Switch
            checked={isOn}
            disabled={isDisabled}
            loading={isLoading}
            checkedChildren="ON"
            unCheckedChildren="OFF"
            onChange={(checked) => handleToggle(row, checked)}
          />
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
              const isOn = optimisticState[row.key] ?? row.onAction !== undefined;
              return (
                <Tag color={isOn ? "success" : "default"}>
                  {isOn ? "ON" : "OFF"}
                </Tag>
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
