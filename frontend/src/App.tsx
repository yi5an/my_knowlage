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
} from "@ant-design/icons";
import { Avatar, Button, Input, Layout, Menu, Space, Tag, Typography } from "antd";
import type { MenuProps } from "antd";
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

const { Content, Header, Sider } = Layout;

const navItems: MenuProps["items"] = [
  { key: "/", icon: <DashboardOutlined />, label: <Link to="/">Dashboard</Link> },
  { key: "/import", icon: <CloudUploadOutlined />, label: <Link to="/import">Import</Link> },
  { key: "/library", icon: <BookOutlined />, label: <Link to="/library">Library</Link> },
  { key: "/reader", icon: <ReadOutlined />, label: <Link to="/reader">Reader</Link> },
  { key: "/graph", icon: <NodeIndexOutlined />, label: <Link to="/graph">Graph</Link> },
  { key: "/search", icon: <SearchOutlined />, label: <Link to="/search">Search</Link> },
  { key: "/research", icon: <FileSearchOutlined />, label: <Link to="/research">Research</Link> },
  { key: "/entity", icon: <StockOutlined />, label: <Link to="/entity">Entity</Link> },
  { key: "/notebooklm", icon: <ApiOutlined />, label: <Link to="/notebooklm">NotebookLM</Link> },
  { key: "/settings", icon: <SettingOutlined />, label: <Link to="/settings">Settings</Link> },
];

function selectedKey(pathname: string): string {
  const match = navItems?.find((item) => {
    if (!item || !("key" in item)) {
      return false;
    }
    const key = String(item.key);
    return key === "/" ? pathname === "/" : pathname.startsWith(key);
  });
  return match && "key" in match ? String(match.key) : "/";
}

export function App() {
  const location = useLocation();

  return (
    <Layout className="app-shell">
      <Sider className="app-sidebar" width={248} breakpoint="lg" collapsedWidth={0}>
        <Link to="/" className="brand">
          <Avatar shape="square" icon={<ApartmentOutlined />} className="brand-mark" />
          <span>
            <Typography.Text className="brand-name">KnowPilot</Typography.Text>
            <Typography.Text className="brand-subtitle">Local knowledge agent</Typography.Text>
          </span>
        </Link>
        <Menu
          className="side-menu"
          mode="inline"
          selectedKeys={[selectedKey(location.pathname)]}
          items={navItems}
        />
        <div className="sidebar-footer">
          <Tag color="processing">Local-first</Tag>
          <Tag color="success">Mock UI</Tag>
        </div>
      </Sider>
      <Layout>
        <Header className="app-header">
          <Input
            className="global-search"
            prefix={<SearchOutlined />}
            placeholder="Search documents, entities, annotations, reports..."
          />
          <Space className="header-actions">
            <Button icon={<ControlOutlined />}>Review queue</Button>
            <Button type="primary" icon={<FileSearchOutlined />}>
              New research
            </Button>
          </Space>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
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
  );
}
