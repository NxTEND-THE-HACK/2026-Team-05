import { Button } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router";

export function BackToDashboard() {
  const navigate = useNavigate();

  return (
    <Button
      type="text"
      icon={<ArrowLeftOutlined />}
      onClick={() => navigate("/")}
      style={{ paddingInline: 0, marginBottom: 8 }}
    >
      Dashboard
    </Button>
  );
}
