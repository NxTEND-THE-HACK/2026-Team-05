import { useState } from "react";
import {
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { PlusOutlined } from "@ant-design/icons";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import dayjs from "dayjs";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { useAppliances, useCreateAppliance } from "~/hooks/useAppliances";
import { queryKeys } from "~/hooks/queryKeys";
import type { Appliance, ControlProvider } from "~/types/backendApi";

const { Title } = Typography;

interface CreateApplianceFormValues {
  name: string;
  category: string;
  controlProvider: ControlProvider;
}

const providerTag: Record<ControlProvider, { color: string; label: string }> = {
  TUYA: { color: "blue", label: "Tuya" },
  ESP32_IR: { color: "purple", label: "赤外線" },
};

export function DevicesPage() {
  const { data: appliances = [], isLoading } = useAppliances();
  const createAppliance = useCreateAppliance();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<CreateApplianceFormValues>();

  const columns: ColumnsType<Appliance> = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, record: Appliance) => (
        <a onClick={() => navigate(`/devices/${record.id}`)}>{name}</a>
      ),
    },
    {
      title: "Category",
      dataIndex: "category",
      key: "category",
      width: 200,
    },
    {
      title: "Control",
      dataIndex: "controlProvider",
      key: "controlProvider",
      width: 140,
      render: (provider: ControlProvider) => {
        const cfg = providerTag[provider] ?? { color: "default", label: provider };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: "Created At",
      dataIndex: "createdAt",
      key: "createdAt",
      width: 200,
      render: (val: string) => dayjs(val).format("YYYY/MM/DD HH:mm"),
    },
  ];

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const created = await createAppliance.mutateAsync({
        name: values.name.trim(),
        category: values.category.trim(),
        controlProvider: values.controlProvider,
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.appliances });
      message.success("デバイスを追加しました");
      form.resetFields();
      setModalOpen(false);
      navigate(`/devices/${created.id}`);
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        err instanceof Error ? err.message : "デバイスの追加に失敗しました",
      );
    }
  };

  const handleClose = () => {
    form.resetFields();
    setModalOpen(false);
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <BackToDashboard />
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          Devices
        </Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalOpen(true)}
        >
          Add Device
        </Button>
      </div>
      <Table
        columns={columns}
        dataSource={appliances}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="middle"
      />
      <Modal
        title="Add Device"
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={handleClose}
        confirmLoading={createAppliance.isPending}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          style={{ marginTop: 16 }}
          initialValues={{ controlProvider: "TUYA" }}
        >
          <Form.Item
            name="name"
            label="Name"
            rules={[{ required: true, message: "名前を入力してください" }]}
          >
            <Input placeholder="例: リビング照明" />
          </Form.Item>
          <Form.Item
            name="category"
            label="Category"
            rules={[{ required: true, message: "カテゴリを入力してください" }]}
          >
            <Input placeholder="例: 照明" />
          </Form.Item>
          <Form.Item
            name="controlProvider"
            label="操作方式"
            rules={[{ required: true, message: "操作方式を選択してください" }]}
          >
            <Select
              options={[
                { label: "Tuya スマートプラグ", value: "TUYA" },
                { label: "ESP32 赤外線コントローラー", value: "ESP32_IR" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
