import { Layout, Typography, Space } from "antd";
import { ApiStatusBadge } from "../dashboard/ApiStatusBadge";

const { Header: AntHeader } = Layout;
const { Text } = Typography;

export function Header() {
  return (
    <AntHeader
      style={{
        background: "#fff",
        padding: "0 24px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderBottom: "1px solid #f0f0f0",
      }}
    >
      <Text strong style={{ fontSize: 16 }}>
        Gesture Smart Home Dashboard
      </Text>
      <ApiStatusBadge />
    </AntHeader>
  );
}
