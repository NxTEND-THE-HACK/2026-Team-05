import { useState } from "react";
import { Button, Card, Col, Empty, Popconfirm, Row, message } from "antd";
import { DeleteOutlined } from "@ant-design/icons";
import { useDeleteAction } from "~/hooks/useActions";
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
  const deleteAction = useDeleteAction();
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

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

  const handleDelete = async (action: IRAction) => {
    setDeletingId(action.id);
    try {
      await deleteAction.mutateAsync({
        actionId: action.id,
        applianceId: action.applianceId,
      });
      message.success(`「${action.name}」を削除しました`);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "削除に失敗しました",
      );
    } finally {
      setDeletingId(null);
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
            <div style={{ display: "flex", gap: 4 }}>
              <Button
                block
                size="middle"
                disabled={disabled || deletingId !== null}
                loading={executingId === action.id}
                onClick={() => handleExecute(action)}
                style={{ minWidth: 0 }}
                title={`repeat: ${action.params.repeat}`}
              >
                {action.name}
              </Button>
              <Popconfirm
                title={`「${action.name}」を削除しますか？`}
                description="このボタンに紐づくモーション設定も削除されます。この操作は元に戻せません。"
                okText="削除"
                cancelText="キャンセル"
                okButtonProps={{ danger: true }}
                onConfirm={() => handleDelete(action)}
                disabled={disabled || executingId !== null || deletingId !== null}
              >
                <Button
                  danger
                  size="middle"
                  icon={<DeleteOutlined />}
                  aria-label={`「${action.name}」を削除`}
                  disabled={disabled || executingId !== null || deletingId !== null}
                  loading={deletingId === action.id}
                />
              </Popconfirm>
            </div>
          </Card>
        </Col>
      ))}
    </Row>
  );
}
