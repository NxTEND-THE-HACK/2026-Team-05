import type { MenuProps } from "antd";
import { Menu } from "antd";
import {
  DashboardOutlined,
  BulbOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router";

type MenuItem = Required<MenuProps>["items"][number];

const menuItems: MenuItem[] = [
  {
    key: "/",
    icon: <DashboardOutlined />,
    label: "Dashboard",
  },
  {
    type: "divider",
  },
  {
    key: "group-devices",
    label: "Devices",
    type: "group",
    children: [
      {
        key: "/device-1",
        icon: <BulbOutlined />,
        label: "Device 1",
      },
      {
        key: "/device-2",
        icon: <BulbOutlined />,
        label: "Device 2",
      },
      {
        key: "/device-3",
        icon: <BulbOutlined />,
        label: "Device 3",
      },
    ],
  },
];

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = location.pathname === "/" ? "/" : location.pathname;

  const onClick: MenuProps["onClick"] = ({ key }) => {
    navigate(key);
  };

  return (
    <>
      <div
        style={{
          height: 64,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#fff",
          fontSize: 18,
          fontWeight: 700,
          borderBottom: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        Smart Home
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[selectedKey]}
        items={menuItems}
        onClick={onClick}
      />
    </>
  );
}
