import { Alert, Space, Tag, Tooltip, Typography } from "antd";
import { useIRHealth } from "~/hooks/useIRController";

const { Text } = Typography;

const stateLabel: Record<string, { color: string; label: string }> = {
  idle: { color: "success", label: "待機中" },
  learning: { color: "warning", label: "学習中" },
  sending: { color: "processing", label: "送信中" },
  error: { color: "error", label: "エラー" },
};

interface IRControllerStatusProps {
  applianceId: string;
}

export function IRControllerStatus({ applianceId }: IRControllerStatusProps) {
  const { data, isLoading, isError, error } = useIRHealth(applianceId);

  if (isLoading) {
    return <Tag>接続確認中...</Tag>;
  }

  if (isError || !data || !data.ok) {
    return (
      <Alert
        type="error"
        showIcon
        message="赤外線コントローラーに接続できません"
        description={error instanceof Error ? error.message : "設定またはネットワークを確認してください"}
      />
    );
  }

  const state = stateLabel[data.state] ?? { color: "default", label: data.state };
  const online = data.wifiConnected;

  return (
    <Space direction="vertical" size={4} style={{ width: "100%" }}>
      <Space size="small" wrap>
        <Tag color={online ? "success" : "error"}>
          {online ? "オンライン" : "オフライン"}
        </Tag>
        <Tag color={state.color}>{state.label}</Tag>
        {data.ip && <Tag>{data.ip}</Tag>}
        {data.firmwareVersion && (
          <Tooltip title="ファームウェア版">
            <Tag>fw {data.firmwareVersion}</Tag>
          </Tooltip>
        )}
        {typeof data.rssi === "number" && (
          <Tooltip title="受信信号強度 (RSSI)">
            <Tag>{data.rssi} dBm</Tag>
          </Tooltip>
        )}
      </Space>
      <Text type="secondary" style={{ fontSize: 12 }}>
        赤外線は一方向通信のため、家電の実際のON/OFF状態は取得できません。
      </Text>
    </Space>
  );
}
