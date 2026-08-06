import { useState } from "react";
import {
  Descriptions,
  Drawer,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { useLogs } from "~/hooks/useLogs";
import type { ActionLog } from "~/types/backendApi";

const { Title } = Typography;

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
    key: "motion",
    render: (_: unknown, record: ActionLog) =>
      record.motionName ?? record.motionCode,
  },
  {
    title: "Action",
    key: "action",
    render: (_: unknown, record: ActionLog) =>
      record.actionName ?? record.actionId ?? "—",
  },
  {
    title: "Camera",
    key: "camera",
    render: (_: unknown, record: ActionLog) =>
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

export function LogsPage() {
  const { data: logs = [], isLoading } = useLogs(200);
  const [selectedLog, setSelectedLog] = useState<ActionLog | null>(null);

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <BackToDashboard />
      <Title level={3} style={{ margin: 0 }}>
        Action Logs
      </Title>
      <Table
        columns={columns}
        dataSource={logs}
        rowKey="id"
        loading={isLoading}
        pagination={{ pageSize: 50, showSizeChanger: false }}
        size="middle"
        onRow={(record) => ({
          onClick: () => setSelectedLog(record),
          style: { cursor: "pointer" },
        })}
      />
      <Drawer
        title="Log Detail"
        open={!!selectedLog}
        onClose={() => setSelectedLog(null)}
        width={480}
      >
        {selectedLog && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="ID">{selectedLog.id}</Descriptions.Item>
            <Descriptions.Item label="Event ID">
              {selectedLog.eventId}
            </Descriptions.Item>
            <Descriptions.Item label="Camera">
              {selectedLog.cameraName ?? selectedLog.cameraId}
            </Descriptions.Item>
            <Descriptions.Item label="Motion">
              {selectedLog.motionName ?? selectedLog.motionCode}
            </Descriptions.Item>
            <Descriptions.Item label="Action">
              {selectedLog.actionName ?? selectedLog.actionId ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="Status">
              <Tag
                color={
                  statusConfig[selectedLog.status]?.color ?? "default"
                }
              >
                {statusConfig[selectedLog.status]?.label ?? selectedLog.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Confidence">—</Descriptions.Item>
            <Descriptions.Item label="Error Message">—</Descriptions.Item>
            <Descriptions.Item label="Detected At">
              {dayjs(selectedLog.detectedAt).format("YYYY/MM/DD HH:mm:ss")}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </Space>
  );
}
