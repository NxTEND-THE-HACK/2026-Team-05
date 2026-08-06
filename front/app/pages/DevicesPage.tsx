import { useState } from "react";
import {
  Button,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { PlusOutlined } from "@ant-design/icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { useAppliances } from "~/hooks/useAppliances";
import { queryKeys } from "~/hooks/queryKeys";
import { request } from "~/services/backendApiClient";
import type { Appliance } from "~/types/backendApi";

const { Title } = Typography;

interface CreateApplianceRequest {
  name: string;
  category: string;
}

const columns: ColumnsType<Appliance> = [
  {
    title: "Name",
    dataIndex: "name",
    key: "name",
  },
  {
    title: "Category",
    dataIndex: "category",
    key: "category",
    width: 200,
  },
  {
    title: "Created At",
    dataIndex: "createdAt",
    key: "createdAt",
    width: 200,
    render: (val: string) => dayjs(val).format("YYYY/MM/DD HH:mm"),
  },
];

export function DevicesPage() {
  const { data: appliances = [], isLoading } = useAppliances();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<CreateApplianceRequest>();

  const createAppliance = useMutation({
    mutationFn: (input: CreateApplianceRequest) =>
      request<Appliance>("/api/appliances", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.appliances });
      message.success("デバイスを追加しました");
    },
  });

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      await createAppliance.mutateAsync(values);
      form.resetFields();
      setModalOpen(false);
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error("デバイスの追加に失敗しました");
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
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
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
        </Form>
      </Modal>
    </Space>
  );
}
