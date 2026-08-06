import { Card, Col, Row, Statistic } from "antd";
import type { ReactNode } from "react";

interface SummaryCardProps {
  title: string;
  value: number;
  icon?: ReactNode;
  onClick?: () => void;
}

export function SummaryCard({ title, value, icon, onClick }: SummaryCardProps) {
  return (
    <Col xs={24} sm={12} md={6}>
      <Card hoverable={!!onClick} onClick={onClick}>
        <Statistic
          title={title}
          value={value}
          prefix={icon}
          styles={{ content: { fontSize: 28 } }}
        />
      </Card>
    </Col>
  );
}
