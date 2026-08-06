import { Layout, Typography, theme } from "antd";
import { ApiStatusBadge } from "../dashboard/ApiStatusBadge";

const { Header: AntHeader } = Layout;
const { Text } = Typography;

export function Header() {
  const { token } = theme.useToken();

  return (
    <AntHeader
      style={{
        background: token.colorBgContainer,
        padding: "0 24px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      <Text strong style={{ fontSize: 18, letterSpacing: 1 }}>
        Remo-Trace
      </Text>
      <ApiStatusBadge />
    </AntHeader>
  );
}
