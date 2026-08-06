import { Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import type { ActionLog } from "~/types/backendApi";

const statusConfig: Record<string, { color: string; label: string }> = {
  SUCCESS: { color: "success", label: "成功" },
  FAILED: { color: "error", label: "失敗" },
  COOLING_DOWN: { color: "warning", label: "クールダウン" },
};

const columns: ColumnsType<ActionLog> = [
  {
    title: "Status",
    dataIndex: "status",
    key: "status",
    width: 120,
    render: (status: string) => {
      const cfg = statusConfig[status] ?? { color: "default", label: status };
      return <Tag color={cfg.color}>{cfg.label}</Tag>;
    },
  },
  {
    title: "Motion",
    dataIndex: "motionName",
    key: "motion",
    render: (_: string | undefined, record: ActionLog) =>
      record.motionName ?? record.motionCode,
  },
  {
    title: "Action",
    dataIndex: "actionName",
    key: "action",
    render: (_: string | undefined, record: ActionLog) =>
      record.actionName ?? (record.actionId ? "—" : "—"),
  },
  {
    title: "Camera",
    dataIndex: "cameraName",
    key: "camera",
    render: (_: string | undefined, record: ActionLog) =>
      record.cameraName ?? record.cameraId,
  },
  {
    title: "Date",
    dataIndex: "detectedAt",
    key: "date",
    width: 180,
    render: (val: string) => dayjs(val).format("YYYY/MM/DD HH:mm:ss"),
  },
];

interface LogsTableProps {
  logs: ActionLog[];
  loading?: boolean;
}

export function LogsTable({ logs, loading }: LogsTableProps) {
  return (
    <Table
      columns={columns}
      dataSource={logs}
      rowKey="id"
      loading={loading}
      pagination={{
        pageSize: 20,
        showSizeChanger: false,
      }}
      size="medium"
    />
  );
}
