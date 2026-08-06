import { useState } from "react";
import {
  Button,
  Card,
  message,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useBindings, useCreateBinding } from "~/hooks/useBindings";
import { useMotions } from "~/hooks/useMotions";
import { useActions } from "~/hooks/useActions";
import { useAppliances } from "~/hooks/useAppliances";
import { NewMotionModal } from "./NewMotionModal";
import type { MotionBinding, Appliance, Motion, Action } from "~/types/backendApi";

interface BindingRow {
  key: string;
  binding: MotionBinding;
  appliance?: Appliance;
  motion?: Motion;
  action?: Action;
}

interface DeviceBindingPanelProps {
  appliances: Appliance[];
  motions: Motion[];
  actions: Action[];
  bindings: MotionBinding[];
  loading?: boolean;
}

export function DeviceBindingPanel({
  appliances,
  motions,
  actions,
  bindings,
  loading,
}: DeviceBindingPanelProps) {
  const [modalOpen, setModalOpen] = useState(false);

  const bindingRows: BindingRow[] = bindings.map((b) => ({
    key: b.id,
    binding: b,
    motion: motions.find((m) => m.id === b.motionId),
    action: actions.find((a) => a.id === b.actionId),
    appliance: appliances.find((a) =>
      actions.find((ac) => ac.id === b.actionId && ac.applianceId === a.id),
    ),
  }));

  const deviceColumns: ColumnsType<Appliance> = [
    { title: "Title", dataIndex: "name", key: "name" },
    {
      title: "Status",
      key: "status",
      render: () => <Tag color="default">オンライン</Tag>,
    },
  ];

  const bindingColumns: ColumnsType<BindingRow> = [
    {
      title: "Device title",
      dataIndex: ["appliance", "name"],
      key: "device",
      render: (_: unknown, row: BindingRow) =>
        row.appliance?.name ?? row.binding.actionId,
    },
    {
      title: "Status",
      key: "status",
      render: (_: unknown, row: BindingRow) => (
        <Tag color={row.binding.isEnabled ? "success" : "default"}>
          {row.binding.isEnabled ? "有効" : "無効"}
        </Tag>
      ),
    },
    {
      title: "Binded Motion",
      key: "motion",
      render: (_: unknown, row: BindingRow) =>
        row.motion?.name ?? row.binding.motionId,
    },
    {
      title: "Del",
      key: "del",
      width: 80,
      render: () => (
        <Popconfirm
          title="この紐付けを削除しますか？"
          onConfirm={() =>
            message.warning("バインディング削除はバックエンド未対応です")
          }
        >
          <Button danger size="small">
            削除
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card title="Devices" size="small">
        <Table
          columns={deviceColumns}
          dataSource={appliances}
          rowKey="id"
          pagination={false}
          size="small"
          loading={loading}
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
