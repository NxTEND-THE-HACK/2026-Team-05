import { useState } from "react";
import { Outlet } from "react-router";
import { Layout, theme } from "antd";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

const { Sider, Content } = Layout;

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const { token } = theme.useToken();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header />
      <Layout style={{ flex: 1, minHeight: 0 }}>
        <Sider
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          breakpoint="lg"
          theme="dark"
          width={240}
          style={{
            borderRight: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Sidebar />
        </Sider>
        <Content
          style={{
            padding: 48,
            background: token.colorBgLayout,
            overflow: "auto",
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
