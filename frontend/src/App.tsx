import {
  ApiOutlined,
  ApartmentOutlined,
  BookOutlined,
  CloudUploadOutlined,
  ControlOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  NodeIndexOutlined,
  ReadOutlined,
  SearchOutlined,
  SettingOutlined,
  StockOutlined,
  YoutubeOutlined,
} from "@ant-design/icons";
import { Avatar, Button, Input, Layout, Menu, Space, Tag, Typography } from "antd";
import type { MenuProps } from "antd";
import zhCN from "antd/locale/zh_CN";
import { ConfigProvider } from "antd";
import { Link, Route, Routes, useLocation } from "react-router-dom";

import { DashboardPage } from "./pages/DashboardPage";
import { EntityPage } from "./pages/EntityPage";
import { GraphPage } from "./pages/GraphPage";
import { ImportPage } from "./pages/ImportPage";
import { LibraryPage } from "./pages/LibraryPage";
import { NotebookPage } from "./pages/NotebookPage";
import { ReaderPage } from "./pages/ReaderPage";
import { ResearchPage } from "./pages/ResearchPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SubscriptionPage } from "./pages/SubscriptionPage";
import { VideoSummaryPage } from "./pages/VideoSummaryPage";
import { YouTubeHubPage } from "./pages/YouTubeHubPage";

const { Content, Header, Sider } = Layout;

const navItems: MenuProps["items"] = [
  { key: "/", icon: <DashboardOutlined />, label: <Link to="/">仪表盘</Link> },
  { key: "/youtube", icon: <YoutubeOutlined />, label: <Link to="/youtube">YouTube</Link> },
  { key: "/youtube/subscriptions", icon: <YoutubeOutlined />, label: <Link to="/youtube/subscriptions">订阅管理</Link> },
  { key: "/import", icon: <CloudUploadOutlined />, label: <Link to="/import">导入</Link> },
  { key: "/library", icon: <BookOutlined />, label: <Link to="/library">文档库</Link> },
  { key: "/reader", icon: <ReadOutlined />, label: <Link to="/reader">阅读</Link> },
  { key: "/graph", icon: <NodeIndexOutlined />, label: <Link to="/graph">知识图谱</Link> },
  { key: "/search", icon: <SearchOutlined />, label: <Link to="/search">搜索</Link> },
  { key: "/research", icon: <FileSearchOutlined />, label: <Link to="/research">研究</Link> },
  { key: "/entity", icon: <StockOutlined />, label: <Link to="/entity">实体</Link> },
  { key: "/notebooklm", icon: <ApiOutlined />, label: <Link to="/notebooklm">NotebookLM</Link> },
  { key: "/settings", icon: <SettingOutlined />, label: <Link to="/settings">设置</Link> },
];

function selectedKey(pathname: string): string {
  // Match the longest nav key that is a prefix of the current path, so that
  // "/youtube/subscriptions" wins over "/youtube" (otherwise the shorter key
  // swallows the longer one and the active highlight is wrong).
  let best: string | null = null;
  for (const item of navItems ?? []) {
    if (!item || !("key" in item)) continue;
    const key = String(item.key);
    const matches = key === "/" ? pathname === "/" : pathname === key || pathname.startsWith(key + "/");
    if (matches && (best === null || key.length > best.length)) {
      best = key;
    }
  }
  return best ?? "/";
}

export function App() {
  const location = useLocation();

  return (
    <ConfigProvider locale={zhCN}>
    <Layout className="app-shell">
      <Sider className="app-sidebar" width={248} breakpoint="lg" collapsedWidth={0}>
        <Link to="/" className="brand">
          <Avatar shape="square" icon={<ApartmentOutlined />} className="brand-mark" />
          <span>
            <Typography.Text className="brand-name">KnowPilot</Typography.Text>
            <Typography.Text className="brand-subtitle">本地知识助手</Typography.Text>
          </span>
        </Link>
        <Menu
          className="side-menu"
          mode="inline"
          selectedKeys={[selectedKey(location.pathname)]}
          items={navItems}
        />
        <div className="sidebar-footer">
          <Tag color="processing">本地优先</Tag>
          <Tag color="success">演示界面</Tag>
        </div>
      </Sider>
      <Layout>
        <Header className="app-header">
          <Input
            className="global-search"
            prefix={<SearchOutlined />}
            placeholder="搜索文档、实体、批注、报告..."
          />
          <Space className="header-actions">
            <Button icon={<ControlOutlined />}>审阅队列</Button>
            <Button type="primary" icon={<FileSearchOutlined />}>
              新建研究
            </Button>
          </Space>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/youtube" element={<YouTubeHubPage />} />
            <Route path="/youtube/subscriptions" element={<SubscriptionPage />} />
            <Route path="/youtube/summary/:documentId" element={<VideoSummaryPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/reader" element={<ReaderPage />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/entity" element={<EntityPage />} />
            <Route path="/entity/:entityId" element={<EntityPage />} />
            <Route path="/notebooklm" element={<NotebookPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
    </ConfigProvider>
  );
}
