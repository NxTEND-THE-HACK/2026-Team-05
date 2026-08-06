import { useEffect, useState } from "react";
import { Badge, Space, Typography } from "antd";
import { getApiBaseUrl } from "~/services/backendApiClient";

const { Text } = Typography;

type HealthStatus = "online" | "offline";

export function ApiStatusBadge() {
  const [status, setStatus] = useState<HealthStatus>("offline");
  const apiBaseUrl = getApiBaseUrl();

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${apiBaseUrl}/healthz`);
        setStatus(res.ok ? "online" : "offline");
      } catch {
        setStatus("offline");
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 10_000);
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  return (
    <Space>
      <Badge
        status={status === "online" ? "success" : "error"}
        text={status === "online" ? "online" : "offline"}
      />
      <Text type="secondary" style={{ fontSize: 12 }}>
        {apiBaseUrl}
      </Text>
    </Space>
  );
}
