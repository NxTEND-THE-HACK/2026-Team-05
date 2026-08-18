import { useMemo } from "react";
import { Button, Form, Modal, Popover, Select, Space, message } from "antd";
import { PlayCircleOutlined } from "@ant-design/icons";
import { useCreateBinding } from "~/hooks/useBindings";
import { getMotionClip, MotionPreview, MotionThumb } from "~/components/motion-preview";
import type { Motion, Action, Appliance } from "~/types/backendApi";

interface NewMotionModalProps {
  open: boolean;
  onClose: () => void;
  motions: Motion[];
  actions: Action[];
  appliances: Appliance[];
}

export function NewMotionModal({
  open,
  onClose,
  motions,
  actions,
  appliances,
}: NewMotionModalProps) {
  const [form] = Form.useForm();
  const createBinding = useCreateBinding();
  const selectedMotionId = Form.useWatch("motionId", form);
  const selectedMotion = motions.find((m) => m.id === selectedMotionId);
  const selectedClip = selectedMotion ? getMotionClip(selectedMotion.code) : undefined;

  const actionOptions = useMemo(() => {
    const map = new Map<string, { label: string; options: { label: string; value: string }[] }>();
    for (const action of actions) {
      const appliance = appliances.find((a) => a.id === action.applianceId);
      const group = appliance?.name ?? action.applianceId;
      if (!map.has(group)) map.set(group, { label: group, options: [] });
      map.get(group)!.options.push({ label: action.name, value: action.id });
    }
    return Array.from(map.values());
  }, [actions, appliances]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      await createBinding.mutateAsync({
        motionId: values.motionId,
        actionId: values.actionId,
      });
      message.success("バインディングを作成しました");
      form.resetFields();
      onClose();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error("バインディング作成に失敗しました");
    }
  };

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      title="New Motion Binding"
      open={open}
      onOk={handleSubmit}
      onCancel={handleClose}
      confirmLoading={createBinding.isPending}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item
          name="motionId"
          label="Motion"
          rules={[{ required: true, message: "モーションを選択してください" }]}
        >
          <Select
            placeholder="モーションを選択"
            options={motions.map((m) => ({
              label: `${m.name} (${m.code})`,
              value: m.id,
            }))}
          />
        </Form.Item>

        {selectedMotion && (
          <Space size="small" align="center" style={{ marginTop: -8, marginBottom: 16 }}>
            <MotionThumb clip={selectedClip} width={40} />
            {selectedClip && (
              <Popover
                title={`${selectedMotion.name} プレビュー`}
                trigger="click"
                destroyTooltipOnHide
                content={<MotionPreview clip={selectedClip} height={280} interactive={false} />}
              >
                <Button size="small" icon={<PlayCircleOutlined />}>
                  プレビュー
                </Button>
              </Popover>
            )}
          </Space>
        )}

        <Form.Item
          name="actionId"
          label="Action"
          rules={[{ required: true, message: "アクションを選択してください" }]}
        >
          <Select
            placeholder="アクションを選択"
            options={actionOptions}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
