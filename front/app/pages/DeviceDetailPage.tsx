import { useMemo, useState } from "react";
import {
  Button,
  Card,
  Descriptions,
  Result,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  PoweroffOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
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
    () =>
      actions.filter((a) => a.applianceId === appliance?.id).sort((a, b) => {
        // Prefer ON before OFF when value is known
        const av = a.params.value === true ? 0 : a.params.value === false ? 1 : 2;
        const bv = b.params.value === true ? 0 : b.params.value === false ? 1 : 2;
        if (av !== bv) return av - bv;
        return a.name.localeCompare(b.name);
      }),
    [actions, appliance?.id],
  );

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

  const handleExecute = async (action: Action) => {
    setExecutingId(action.id);
    try {
      const result = await executeAction.mutateAsync(action.id);
      if (result.success) {
        message.success(`「${action.name}」を実行しました`);
      } else {
        message.error(
          result.message
            ? `実行失敗: ${result.message}`
            : `「${action.name}」の実行に失敗しました`,
        );
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "実行に失敗しました";
      message.error(msg);
    } finally {
      setExecutingId(null);
    }
  };

  const actionColumns: ColumnsType<Action> = [
    {
      title: "Action",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "Type",
      key: "type",
      width: 120,
      render: (_: unknown, action: Action) => {
        if (action.params.value === true) {
          return <Tag color="success">ON</Tag>;
        }
        if (action.params.value === false) {
          return <Tag color="default">OFF</Tag>;
        }
        return <Tag>OTHER</Tag>;
      },
    },
    {
      title: "Control",
      key: "control",
      width: 140,
      render: (_: unknown, action: Action) => {
        const isOn = action.params.value === true;
        const isOff = action.params.value === false;
        return (
          <Button
            type={isOn ? "primary" : isOff ? "default" : "primary"}
            danger={isOff}
            size="small"
            icon={isOn ? <ThunderboltOutlined /> : <PoweroffOutlined />}
            loading={executingId === action.id}
            disabled={executingId !== null && executingId !== action.id}
            onClick={() => handleExecute(action)}
          >
            {isOn ? "ON" : isOff ? "OFF" : "実行"}
          </Button>
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
            <Tag color="success">オンライン</Tag>
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
          dataSource={deviceActions}
          rowKey="id"
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
