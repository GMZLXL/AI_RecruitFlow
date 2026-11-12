import { Typography } from 'antd';
const { Title, Text } = Typography;
export default function PageHead({ title, desc }: {title: string; desc?: string}) {
  return <div className="page-head"><Title level={3} style={{ margin: 0 }}>{title}</Title>{desc && <Text type="secondary">{desc}</Text>}</div>;
}
