import { Component, type ReactNode } from 'react';
import { Button, Result } from 'antd';

export default class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <Result status="error" title="当前内容未能显示" subTitle="业务记录已保留，请重新加载页面后重试。"
      extra={<Button onClick={() => window.location.reload()}>重新加载页面</Button>} /> : this.props.children;
  }
}
