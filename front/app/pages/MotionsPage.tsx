import { useState } from "react";
import { Button, Modal, Space, Table, Typography } from "antd";
import { PlayCircleOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { BackToDashboard } from "~/components/common/BackToDashboard";
import { getMotionClip, MotionPreview, MotionThumb } from "~/components/motion-preview";
import { useMotions } from "~/hooks/useMotions";
import type { Motion } from "~/types/backendApi";

const { Title, Text } = Typography;

export function MotionsPage() {
  const { data: motions = [], isLoading } = useMotions();
  const [previewMotion, setPreviewMotion] = useState<Motion | null>(null);

  const previewClip = previewMotion ? getMotionClip(previewMotion.code) : undefined;

  const columns: ColumnsType<Motion> = [
    {
      title: "Preview",
      key: "preview",
      width: 120,
      render: (_: unknown, motion: Motion) => {
        const clip = getMotionClip(motion.code);
        return (
          <Space size="small" align="center">
            <MotionThumb clip={clip} width={44} />
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              disabled={!clip}
              onClick={() => setPreviewMotion(motion)}
              aria-label={`${motion.name} の3Dプレビューを再生`}
            />
          </Space>
        );
      },
    },
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      width: 200,
    },
    {
      title: "Code",
      dataIndex: "code",
      key: "code",
      width: 240,
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
    },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <BackToDashboard />
      <Title level={3} style={{ margin: 0 }}>
        Motions
      </Title>
      <Table
        columns={columns}
        dataSource={motions}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="middle"
      />

      <Modal
        open={previewMotion !== null}
        title={previewMotion ? `${previewMotion.name} (${previewMotion.code})` : ""}
        footer={null}
        width={520}
        onCancel={() => setPreviewMotion(null)}
        destroyOnHidden
      >
        {previewMotion && (
          <Space direction="vertical" size="small" style={{ width: "100%" }}>
            {previewClip ? (
              <MotionPreview clip={previewClip} height={360} />
            ) : (
              <MotionThumb clip={undefined} width={120} />
            )}
            <Text type="secondary">{previewMotion.description}</Text>
          </Space>
        )}
      </Modal>
    </Space>
  );
}
