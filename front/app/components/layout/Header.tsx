import { Layout, theme } from "antd";
import { ApiStatusBadge } from "../dashboard/ApiStatusBadge";

const { Header: AntHeader } = Layout;

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
      <img
        src="/remotrace-wordmark.svg"
        alt="Remo-Trace"
        style={{
          display: "block",
          height: 36,
          width: "auto",
          maxWidth: "55vw",
          objectFit: "contain",
          flexShrink: 1,
        }}
      />
      <ApiStatusBadge />
    </AntHeader>
  );
}
