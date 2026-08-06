import { useMemo } from "react";
import {
  Card,
  Descriptions,
  Result,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useParams } from "react-router";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { useAppliances } from "~/hooks/useAppliances";
import { useBindings } from "~/hooks/useBindings";
import { useActions } from "~/hooks/useActions";
import { useMotions } from "~/hooks/useMotions";
import type { MotionBinding, Motion, Action } from "~/types/backendApi";

const { Title } = Typography;

interface BindingRow {
  key: string;
  binding: MotionBinding;
  motion?: Motion;
  action?: Action;
}

const columns: ColumnsType<BindingRow> = [
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
  const { data: actions = [], isLoading: actionsLoading } = useActions();
  const { data: motions = [], isLoading: motionsLoading } = useMotions();

  const loading =
    appliancesLoading || bindingsLoading || actionsLoading || motionsLoading;

  const appliance = useMemo(
    () => appliances.find((a) => a.id === deviceId),
    [appliances, deviceId],
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
      <Card title="Binded Motions">
        <Table
          columns={columns}
          dataSource={bindingRows}
          rowKey="key"
          pagination={false}
          size="middle"
          locale={{ emptyText: "このデバイスにバインドされたモーションはありません" }}
        />
      </Card>
    </Space>
  );
}
