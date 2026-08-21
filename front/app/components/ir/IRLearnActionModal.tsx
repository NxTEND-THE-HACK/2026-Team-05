import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Spin,
  Typography,
  message,
} from "antd";
import { useConfirmIRLearning } from "~/hooks/useIRController";
import {
  getIRLearningStatus,
  startIRLearning,
  stopIRLearning,
} from "~/services/backendApiClient";
import type { IRLearnCapture } from "~/types/backendApi";

const { Text } = Typography;

type Phase = "idle" | "starting" | "learning" | "captured" | "error";

interface LearnFormValues {
  name: string;
  repeat: number;
  timeoutSeconds: number;
}

interface IRLearnActionModalProps {
  applianceId: string;
  open: boolean;
  onClose: () => void;
}

export function IRLearnActionModal({
  applianceId,
  open,
  onClose,
}: IRLearnActionModalProps) {
  const [form] = Form.useForm<LearnFormValues>();
  const confirmLearning = useConfirmIRLearning();

  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [capture, setCapture] = useState<IRLearnCapture | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopPending = useRef<Promise<unknown> | null>(null);

  const clearPolling = useCallback(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const stopLearning = useCallback(
    (id: string) => {
      if (stopPending.current) return;
      stopPending.current = stopIRLearning(applianceId, id).catch(() => {
        // タイムアウトや未完了でも停止はベストエフォートで続行する。
      });
    },
    [applianceId],
  );

  const reset = useCallback(() => {
    clearPolling();
    setPhase("idle");
    setSessionId(null);
    setCapture(null);
    setErrorMessage(null);
    stopPending.current = null;
    form.resetFields();
    form.setFieldsValue({ timeoutSeconds: 30, repeat: 1 });
  }, [clearPolling, form]);

  useEffect(() => {
    if (open) {
      reset();
    } else {
      clearPolling();
    }
  }, [open, reset, clearPolling]);

  const handleStart = async () => {
    let timeoutSeconds = 30;
    try {
      const values = await form.validateFields(["timeoutSeconds"]);
      timeoutSeconds = values.timeoutSeconds ?? 30;
    } catch {
      return;
    }
    setPhase("starting");
    setErrorMessage(null);
    try {
      const session = await startIRLearning(applianceId, timeoutSeconds);
      setSessionId(session.sessionId);
      setPhase("learning");
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "学習の開始に失敗しました",
      );
      setPhase("error");
    }
  };

  const pollStatus = useCallback(async () => {
    try {
      const session = await getIRLearningStatus(applianceId);
      if (session.state === "captured" && session.capture) {
        clearPolling();
        setSessionId(session.sessionId);
        setCapture(session.capture);
        setPhase("captured");
      }
      // state === "learning" は継続してポーリングする。
    } catch (err) {
      clearPolling();
      setErrorMessage(
        err instanceof Error ? err.message : "学習状態の取得に失敗しました",
      );
      setPhase("error");
    }
  }, [applianceId, clearPolling]);

  useEffect(() => {
    if (phase !== "learning") return;
    pollStatus();
    pollTimer.current = setInterval(pollStatus, 700);
    return () => clearPolling();
  }, [phase, pollStatus, clearPolling]);

  const handleSave = async () => {
    let values: LearnFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    if (!sessionId || !capture) {
      setErrorMessage("受信結果が見つかりません。学習をやり直してください");
      setPhase("error");
      return;
    }
    try {
      await confirmLearning.mutateAsync({
        applianceId,
        input: {
          sessionId,
          captureId: capture.captureId,
          name: values.name,
          repeat: values.repeat,
        },
      });
      message.success("赤外線ボタンを登録しました");
      reset();
      onClose();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "ボタンの保存に失敗しました",
      );
    }
  };

  const handleCancel = () => {
    if (sessionId && (phase === "learning" || phase === "captured")) {
      stopLearning(sessionId);
    }
    reset();
    onClose();
  };

  const footer = (
    <Space>
      <Button onClick={handleCancel}>キャンセル</Button>
      {phase === "idle" && (
        <Button type="primary" onClick={handleStart}>
          学習を開始
        </Button>
      )}
      {phase === "learning" && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          赤外線信号を待っています...
        </Text>
      )}
      {phase === "captured" && (
        <Button
          type="primary"
          loading={confirmLearning.isPending}
          onClick={handleSave}
        >
          保存
        </Button>
      )}
      {phase === "error" && (
        <Button type="primary" onClick={reset}>
          再試行
        </Button>
      )}
    </Space>
  );

  return (
    <Modal
      title="赤外線ボタンを登録"
      open={open}
      onCancel={handleCancel}
      footer={footer}
      destroyOnHidden
      width={560}
    >
      {phase === "idle" && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon
            message="学習の手順"
            description="1. タイムアウト時間を設定して「学習を開始」を押す。2. リモコンのボタンを赤外線受信機に向けて押す。3. 受信した信号に名前を付けて保存する。"
          />
          <Form form={form} layout="vertical">
            <Form.Item
              name="timeoutSeconds"
              label="学習タイムアウト（秒）"
              rules={[{ required: true, message: "タイムアウトを入力してください" }]}
            >
              <InputNumber min={5} max={120} style={{ width: 160 }} />
            </Form.Item>
          </Form>
        </Space>
      )}

      {phase === "starting" && (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin />
          <div style={{ marginTop: 12 }}>学習を開始しています...</div>
        </div>
      )}

      {phase === "learning" && (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}>
            リモコンのボタンを押して、赤外線信号を送信してください。
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            長押しによるリピート信号は登録されません。
          </Text>
        </div>
      )}

      {phase === "captured" && capture && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Alert
            type="success"
            showIcon
            message="信号を受信しました"
            description="この信号に名前を付けて保存します。"
          />
          <Descriptions
            column={2}
            size="small"
            bordered
            items={[
              { key: "protocol", label: "プロトコル", children: capture.signal.protocol },
              { key: "bits", label: "ビット数", children: capture.signal.bits ?? "—" },
              { key: "code", label: "コード", children: capture.signal.code ?? "—" },
              { key: "address", label: "アドレス", children: capture.signal.address ?? "—" },
              { key: "command", label: "コマンド", children: capture.signal.command ?? "—" },
              { key: "carrierHz", label: "搬送波", children: `${capture.signal.carrierHz} Hz` },
            ]}
          />
          {capture.signal.raw && capture.signal.raw.length > 0 && (
            <Collapse
              size="small"
              items={[
                {
                  key: "raw",
                  label: "Raw データ (詳細)",
                  children: (
                    <Text
                      code
                      style={{ fontSize: 11, wordBreak: "break-all" }}
                    >
                      [{capture.signal.raw.join(", ")}]
                    </Text>
                  ),
                },
              ]}
            />
          )}
          <Form form={form} layout="vertical">
            <Form.Item
              name="name"
              label="ボタン名"
              rules={[
                { required: true, message: "ボタン名を入力してください" },
                { max: 100, message: "100文字以内で入力してください" },
              ]}
            >
              <Input placeholder="例: 電源" />
            </Form.Item>
            <Form.Item
              name="repeat"
              label="送信回数 (repeat)"
              rules={[{ required: true, message: "送信回数を入力してください" }]}
            >
              <InputNumber min={1} max={5} style={{ width: 160 }} />
            </Form.Item>
          </Form>
        </Space>
      )}

      {phase === "error" && (
        <Alert
          type="error"
          showIcon
          message="学習に失敗しました"
          description={errorMessage ?? "タイムアウトまたは通信エラーが発生しました。"}
        />
      )}
    </Modal>
  );
}
