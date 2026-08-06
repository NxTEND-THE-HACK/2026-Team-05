import { useState } from "react";
import { Outlet } from "react-router";
import { Layout, theme } from "antd";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

const { Sider, Content } = Layout;

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const { token } = theme.useToken();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        theme="dark"
        width={240}
      >
        <Sidebar />
      </Sider>
      <Layout>
        <Header />
        <Content style={{ padding: 24, background: token.colorBgLayout }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
