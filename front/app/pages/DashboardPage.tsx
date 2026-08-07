import { Row, Space, Typography } from "antd";
import {
  DashboardOutlined,
  BulbOutlined,
  LinkOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router";
import { useMotions } from "~/hooks/useMotions";
import { useAppliances } from "~/hooks/useAppliances";
import { useBindings } from "~/hooks/useBindings";
import { useLogs } from "~/hooks/useLogs";
import { SummaryCard } from "../components/dashboard/SummaryCard";
import { LogsTable } from "../components/dashboard/LogsTable";

const { Title } = Typography;

export function DashboardPage() {
  const navigate = useNavigate();
  const { data: motions = [], isLoading: motionsLoading } = useMotions();
  const { data: appliances = [], isLoading: appliancesLoading } =
    useAppliances();
  const { data: bindings = [], isLoading: bindingsLoading } = useBindings();
  const { data: logs = [], isLoading: logsLoading } = useLogs(100);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {/* Summary Cards */}
      <Row gutter={[16, 16]}>
        <SummaryCard
          title="Motions"
          value={motions.length}
          icon={<DashboardOutlined />}
          onClick={() => navigate("/motions")}
          loading={motionsLoading}
        />
        <SummaryCard
          title="Devices"
          value={appliances.length}
          icon={<BulbOutlined />}
          onClick={() => navigate("/devices")}
          loading={appliancesLoading}
        />
        <SummaryCard
          title="Bindings"
          value={bindings.length}
          icon={<LinkOutlined />}
          onClick={() => navigate("/bindings")}
          loading={bindingsLoading}
        />
        <SummaryCard
          title="Recent Logs"
          value={logs.length}
          icon={<FileTextOutlined />}
          onClick={() => navigate("/logs")}
          loading={logsLoading}
        />
      </Row>

      {/* Recent Logs */}
      <div>
        <Title level={4}>Recent Logs</Title>
        <LogsTable logs={logs} loading={logsLoading} />
      </div>
    </Space>
  );
}
