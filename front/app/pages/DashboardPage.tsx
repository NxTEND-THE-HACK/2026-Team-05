import { Row, Space, Typography } from "antd";
import {
  DashboardOutlined,
  BulbOutlined,
  LinkOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { useMotions } from "~/hooks/useMotions";
import { useAppliances } from "~/hooks/useAppliances";
import { useActions } from "~/hooks/useActions";
import { useBindings } from "~/hooks/useBindings";
import { useLogs } from "~/hooks/useLogs";
import { SummaryCard } from "../components/dashboard/SummaryCard";
import { LogsTable } from "../components/dashboard/LogsTable";
import { DeviceBindingPanel } from "../components/dashboard/DeviceBindingPanel";

const { Title } = Typography;

export function DashboardPage() {
  const { data: motions = [], isLoading: motionsLoading } = useMotions();
  const { data: appliances = [], isLoading: appliancesLoading } =
    useAppliances();
  const { data: actions = [], isLoading: actionsLoading } = useActions();
  const { data: bindings = [], isLoading: bindingsLoading } = useBindings();
  const { data: logs = [], isLoading: logsLoading } = useLogs(100);

  const loading =
    motionsLoading ||
    appliancesLoading ||
    actionsLoading ||
    bindingsLoading ||
    logsLoading;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {/* Summary Cards */}
      <Row gutter={[16, 16]}>
        <SummaryCard
          title="Motions"
          value={motions.length}
          icon={<DashboardOutlined />}
        />
        <SummaryCard
          title="Devices"
          value={appliances.length}
          icon={<BulbOutlined />}
        />
        <SummaryCard
          title="Bindings"
          value={bindings.length}
          icon={<LinkOutlined />}
        />
        <SummaryCard
          title="Recent Logs"
          value={logs.length}
          icon={<FileTextOutlined />}
        />
      </Row>

      {/* Recent Logs */}
      <div>
        <Title level={4}>Recent Logs</Title>
        <LogsTable logs={logs} loading={logsLoading} />
      </div>

      {/* Device & Binding Management */}
      <div>
        <Title level={4}>Device & Binding Management</Title>
        <DeviceBindingPanel
          appliances={appliances}
          motions={motions}
          actions={actions}
          bindings={bindings}
          loading={loading}
        />
      </div>
    </Space>
  );
}
