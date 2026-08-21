import { useState } from "react";
import { Button, Card, Col, Empty, Row, message } from "antd";
import { useExecuteAction } from "~/hooks/useExecuteAction";
import type { IRAction } from "~/types/backendApi";

interface IRActionButtonGridProps {
  actions: IRAction[];
  disabled?: boolean;
  loading?: boolean;
}

export function IRActionButtonGrid({
  actions,
  disabled,
  loading,
}: IRActionButtonGridProps) {
  const executeAction = useExecuteAction();
  const [executingId, setExecutingId] = useState<string | null>(null);

  const handleExecute = async (action: IRAction) => {
    setExecutingId(action.id);
    try {
      const result = await executeAction.mutateAsync(action.id);
      if (result.success) {
        message.success(`「${action.name}」を送信しました`);
      } else {
        message.error(
          result.message
            ? `送信失敗: ${result.message}`
            : `「${action.name}」の送信に失敗しました`,
        );
      }
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "送信に失敗しました",
      );
    } finally {
      setExecutingId(null);
    }
  };

  if (!loading && actions.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="登録済みの赤外線ボタンがありません。「＋ ボタンを登録」から学習してください。"
      />
    );
  }

  return (
    <Row gutter={[8, 8]}>
      {actions.map((action) => (
        <Col key={action.id} xs={12} sm={8} md={6}>
          <Card size="small" styles={{ body: { padding: 8 } }}>
            <Button
              block
              size="middle"
              disabled={disabled}
              loading={executingId === action.id}
              onClick={() => handleExecute(action)}
              title={`repeat: ${action.params.repeat}`}
            >
              {action.name}
            </Button>
          </Card>
        </Col>
      ))}
    </Row>
  );
}
