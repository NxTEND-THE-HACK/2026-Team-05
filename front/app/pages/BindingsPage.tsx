import { useMemo, useState } from "react";
import {
  Button,
  Card,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { PlusOutlined } from "@ant-design/icons";
import { useMotions } from "~/hooks/useMotions";
import { useAppliances } from "~/hooks/useAppliances";
import { useActions } from "~/hooks/useActions";
import { useBindings, useDeleteBinding } from "~/hooks/useBindings";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { getMotionClip, MotionThumb } from "~/components/motion-preview";
import { NewMotionModal } from "../components/dashboard/NewMotionModal";
import type { MotionBinding, Appliance, Motion, Action } from "~/types/backendApi";

const { Title } = Typography;

interface BindingRow {
  key: string;
  binding: MotionBinding;
  appliance?: Appliance;
  motion?: Motion;
  action?: Action;
}

export function BindingsPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const { data: motions = [] } = useMotions();
  const { data: appliances = [] } = useAppliances();
  const { data: actions = [] } = useActions();
  const { data: bindings = [], isLoading: bindingsLoading } = useBindings();
  const deleteMutation = useDeleteBinding();
  const loading = bindingsLoading;

  const bindingRows: BindingRow[] = useMemo(
    () =>
      bindings.map((b) => ({
        key: b.id,
        binding: b,
        motion: motions.find((m) => m.id === b.motionId),
        action: actions.find((a) => a.id === b.actionId),
        appliance: appliances.find(
          (a) =>
            actions.find(
              (ac) => ac.id === b.actionId && ac.applianceId === a.id,
            ),
        ),
      })),
    [bindings, motions, actions, appliances],
  );

  const deviceColumns: ColumnsType<Appliance> = [
    { title: "Name", dataIndex: "name", key: "name" },
    { title: "Category", dataIndex: "category", key: "category" },
    {
      title: "Status",
      key: "status",
      width: 120,
      render: () => <Tag color="success">オンライン</Tag>,
    },
  ];

  const bindingColumns: ColumnsType<BindingRow> = [
    {
      title: "Device",
      key: "device",
      render: (_: unknown, row: BindingRow) =>
        row.appliance?.name ?? row.binding.actionId,
    },
    {
      title: "Status",
      key: "status",
      width: 120,
      render: (_: unknown, row: BindingRow) => (
        <Tag color={row.binding.isEnabled ? "success" : "default"}>
          {row.binding.isEnabled ? "有効" : "無効"}
        </Tag>
      ),
    },
    {
      title: "Bound Motion",
      key: "motion",
      render: (_: unknown, row: BindingRow) => {
        const clip = row.motion ? getMotionClip(row.motion.code) : undefined;
        return (
          <Space size="small" align="center">
            {clip && <MotionThumb clip={clip} width={26} />}
            {row.motion?.name ?? row.binding.motionId}
          </Space>
        );
      },
    },
    {
      title: "Action",
      key: "action",
      render: (_: unknown, row: BindingRow) =>
        row.action?.name ?? row.binding.actionId,
    },
    {
      title: "Del",
      key: "del",
      width: 80,
      render: (_: unknown, row: BindingRow) => (
        <Popconfirm
          title="この紐付けを削除しますか？"
          onConfirm={async () => {
            try {
              await deleteMutation.mutateAsync(row.binding.id);
              message.success("バインディングを削除しました");
            } catch (error) {
              message.error(
                error instanceof Error
                  ? error.message
                  : "バインディングの削除に失敗しました",
              );
            }
          }}
        >
          <Button danger size="small" loading={deleteMutation.isPending}>
            削除
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <BackToDashboard />
      <Title level={3} style={{ margin: 0 }}>
        Device & Binding Management
      </Title>
      <Card title="Devices" size="small">
        <Table
          columns={deviceColumns}
          dataSource={appliances}
          rowKey="id"
          pagination={false}
          size="small"
        />
      </Card>
      <Card
        title="Bindings"
        size="small"
        extra={
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setModalOpen(true)}
          >
            New Motion
          </Button>
        }
      >
        <Table
          columns={bindingColumns}
          dataSource={bindingRows}
          rowKey="key"
          pagination={false}
          size="small"
          loading={loading}
        />
      </Card>
      <NewMotionModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        motions={motions}
        actions={actions}
        appliances={appliances}
      />
    </Space>
  );
}
