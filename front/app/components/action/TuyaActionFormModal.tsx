import { Form, Input, Modal, Select, Switch, message } from "antd";
import { useCreateAction } from "~/hooks/useActions";

interface TuyaActionFormValues {
  name: string;
  value: boolean;
  switchCode?: string;
  deviceIdEnv?: string;
  deviceId?: string;
}

interface TuyaActionFormModalProps {
  applianceId: string;
  open: boolean;
  onClose: () => void;
}

export function TuyaActionFormModal({
  applianceId,
  open,
  onClose,
}: TuyaActionFormModalProps) {
  const [form] = Form.useForm<TuyaActionFormValues>();
  const createAction = useCreateAction();

  const handleSubmit = async () => {
    let values: TuyaActionFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    if (values.deviceIdEnv && values.deviceId) {
      message.error("デバイスIDは環境変数と直接指定のどちらか一方だけ指定してください");
      return;
    }
    try {
      await createAction.mutateAsync({
        applianceId,
        name: values.name.trim(),
        providerType: "TUYA",
        params: {
          deviceIdEnv: values.deviceIdEnv || undefined,
          deviceId: values.deviceId || undefined,
          switchCode: values.switchCode?.trim() || undefined,
          value: values.value,
        },
      });
      message.success("アクションを追加しました");
      form.resetFields();
      onClose();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "アクションの追加に失敗しました",
      );
    }
  };

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      title="操作を追加"
      open={open}
      onOk={handleSubmit}
      onCancel={handleClose}
      confirmLoading={createAction.isPending}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        style={{ marginTop: 16 }}
        initialValues={{ value: true, switchCode: "switch" }}
      >
        <Form.Item
          name="name"
          label="操作名"
          rules={[{ required: true, message: "操作名を入力してください" }]}
        >
          <Input placeholder="例: 照明 オン" />
        </Form.Item>
        <Form.Item
          name="value"
          label="操作 (ON/OFF)"
          valuePropName="checked"
          rules={[{ required: true }]}
        >
          <Switch
            checkedChildren="ON"
            unCheckedChildren="OFF"
          />
        </Form.Item>
        <Form.Item
          name="switchCode"
          label="スイッチコード"
          tooltip="Tuya の電源DPコード。省略時は switch が使われます。"
        >
          <Input placeholder="switch" />
        </Form.Item>
        <Form.Item
          name="deviceIdEnv"
          label="デバイスID (環境変数)"
          tooltip="deviceId と同時には指定できません。"
        >
          <Select
            allowClear
            placeholder="未指定"
            options={["PLUG_A_ID", "PLUG_B_ID", "PLUG_C_ID"].map((v) => ({
              label: v,
              value: v,
            }))}
          />
        </Form.Item>
        <Form.Item
          name="deviceId"
          label="デバイスID (直接指定)"
          tooltip="deviceIdEnv と同時には指定できません。"
        >
          <Input placeholder="tuya-device-id" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
