import { Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { useMotions } from "~/hooks/useMotions";
import type { Motion } from "~/types/backendApi";

const { Title } = Typography;

const columns: ColumnsType<Motion> = [
  {
    title: "Name",
    dataIndex: "name",
    key: "name",
    width: 200,
  },
  {
    title: "Code",
    dataIndex: "code",
    key: "code",
    width: 240,
  },
  {
    title: "Description",
    dataIndex: "description",
    key: "description",
  },
];

export function MotionsPage() {
  const { data: motions = [], isLoading } = useMotions();

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <BackToDashboard />
      <Title level={3} style={{ margin: 0 }}>
        Motions
      </Title>
      <Table
        columns={columns}
        dataSource={motions}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="middle"
      />
    </Space>
  );
}
