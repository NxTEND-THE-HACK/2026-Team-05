import { useMemo } from "react";
import type { MenuProps } from "antd";
import { Menu } from "antd";
import {
  DashboardOutlined,
  BulbOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router";
import { useAppliances } from "~/hooks/useAppliances";

type MenuItem = Required<MenuProps>["items"][number];

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: appliances = [] } = useAppliances();

  const menuItems: MenuItem[] = useMemo(() => {
    return [
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
        children: appliances.map((appliance) => ({
          key: `/devices/${appliance.id}`,
          icon: <BulbOutlined />,
          label: appliance.name,
        })),
      },
    ];
  }, [appliances]);

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
          letterSpacing: 1,
        }}
      >
        Remo-Trace
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
