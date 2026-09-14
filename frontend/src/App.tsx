import {
  ApiOutlined,
  ApartmentOutlined,
  BookOutlined,
  CloudUploadOutlined,
  ControlOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  FundProjectionScreenOutlined,
  NodeIndexOutlined,
  ReadOutlined,
  SearchOutlined,
  ShareAltOutlined,
  SettingOutlined,
  StockOutlined,
  YoutubeOutlined,
} from "@ant-design/icons";
import { Avatar, Button, Input, Layout, Menu, Space, Tag, Typography } from "antd";
import type { MenuProps } from "antd";
import zhCN from "antd/locale/zh_CN";
import { ConfigProvider } from "antd";
import { Link, Route, Routes, useLocation } from "react-router-dom";

import { CompanionDrawer } from "./components/companion/CompanionDrawer";
import { CompanionProvider } from "./components/companion/CompanionProvider";
import { DashboardPage } from "./pages/DashboardPage";
import { EntityPage } from "./pages/EntityPage";
import { GraphPage } from "./pages/GraphPage";
import { ImportPage } from "./pages/ImportPage";
import { InformationEdgePage } from "./pages/InformationEdgePage";
import { IntelligenceFlowPage } from "./pages/IntelligenceFlowPage";
import { InvestmentCalendarPage } from "./pages/InvestmentCalendarPage";
import { InvestmentClaimsPage } from "./pages/InvestmentClaimsPage";
import { InvestmentDashboardPage } from "./pages/InvestmentDashboardPage";
import { InvestmentDigestPage } from "./pages/InvestmentDigestPage";
import { InvestmentItemsPage } from "./pages/InvestmentItemsPage";
import { InvestmentSourcesPage } from "./pages/InvestmentSourcesPage";
import { InvestmentThemesPage } from "./pages/InvestmentThemesPage";
import { InvestmentThesesPage } from "./pages/InvestmentThesesPage";
import { InvestmentWatchlistPage } from "./pages/InvestmentWatchlistPage";
import { LibraryPage } from "./pages/LibraryPage";
import { ModelManagementPage } from "./pages/ModelManagementPage";
import { ProvenanceGraphPage } from "./pages/ProvenanceGraphPage";
import { NotebookPage } from "./pages/NotebookPage";
import { ReaderPage } from "./pages/ReaderPage";
import { ResearchPage } from "./pages/ResearchPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SubscriptionPage } from "./pages/SubscriptionPage";
import { VideoSummaryPage } from "./pages/VideoSummaryPage";
import { YouTubeHubPage } from "./pages/YouTubeHubPage";

const { Content, Header, Sider } = Layout;

const primaryNavItems: MenuProps["items"] = [
  { key: "/", icon: <DashboardOutlined />, label: <Link to="/">情报流</Link> },
  {
    key: "/investment/watchlist",
    icon: <StockOutlined />,
    label: <Link to="/investment/watchlist">观察对象</Link>,
  },
  {
    key: "/investment/claims",
    icon: <FundProjectionScreenOutlined />,
    label: <Link to="/investment/claims">假设验证</Link>,
  },
  {
    key: "/investment/digest",
    icon: <ReadOutlined />,
    label: <Link to="/investment/digest">研究简报</Link>,
  },
  {
    key: "/investment/accounts",
    icon: <ShareAltOutlined />,
    label: <Link to="/investment/accounts">账号发现</Link>,
  },
  { key: "/youtube", icon: <YoutubeOutlined />, label: <Link to="/youtube">YouTube 观点</Link> },
  {
    key: "/investment/sources",
    icon: <CloudUploadOutlined />,
    label: <Link to="/investment/sources">数据源</Link>,
  },
];

const auxiliaryNavItems: MenuProps["items"] = [
  { key: "/investment", label: <Link to="/investment">旧版投资工作台</Link> },
  { key: "/investment/edge", label: <Link to="/investment/edge">信息差系统</Link> },
  { key: "/investment/themes", label: <Link to="/investment/themes">主题中心</Link> },
  { key: "/investment/items", label: <Link to="/investment/items">投资信息</Link> },
  { key: "/investment/theses", label: <Link to="/investment/theses">投资假设</Link> },
  { key: "/investment/calendar", label: <Link to="/investment/calendar">宏观日历</Link> },
  { key: "/youtube/subscriptions", label: <Link to="/youtube/subscriptions">YouTube 订阅管理</Link> },
  { key: "/import", icon: <CloudUploadOutlined />, label: <Link to="/import">导入</Link> },
  { key: "/library", icon: <BookOutlined />, label: <Link to="/library">文档库</Link> },
  { key: "/reader", icon: <ReadOutlined />, label: <Link to="/reader">阅读</Link> },
  { key: "/graph", icon: <NodeIndexOutlined />, label: <Link to="/graph">知识图谱</Link> },
  { key: "/provenance", icon: <ShareAltOutlined />, label: <Link to="/provenance">溯源图</Link> },
  { key: "/search", icon: <SearchOutlined />, label: <Link to="/search">搜索</Link> },
  { key: "/research", icon: <FileSearchOutlined />, label: <Link to="/research">深度研究</Link> },
  { key: "/entity", icon: <StockOutlined />, label: <Link to="/entity">实体</Link> },
  { key: "/notebooklm", icon: <ApiOutlined />, label: <Link to="/notebooklm">NotebookLM</Link> },
  { key: "/settings", icon: <SettingOutlined />, label: <Link to="/settings">设置</Link> },
];

const navItems: MenuProps["items"] = [
  ...primaryNavItems,
  { key: "support", label: "辅助", children: auxiliaryNavItems },
];

const navKeys = [
  ...primaryNavItems.map((item) => (item && "key" in item ? String(item.key) : "")),
  ...auxiliaryNavItems.map((item) => (item && "key" in item ? String(item.key) : "")),
];
const auxiliaryNavKeys = auxiliaryNavItems.map((item) =>
  item && "key" in item ? String(item.key) : "",
);

function selectedKey(pathname: string): string {
  // Match the longest nav key that is a prefix of the current path, so that
  // "/youtube/subscriptions" wins over "/youtube" (otherwise the shorter key
  // swallows the longer one and the active highlight is wrong).
  let best: string | null = null;
  for (const key of navKeys) {
    if (!key || key === "support") continue;
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
    <CompanionProvider>
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
          defaultOpenKeys={
            auxiliaryNavKeys.some(
              (key) => key && (location.pathname === key || location.pathname.startsWith(`${key}/`)),
            )
              ? ["support"]
              : []
          }
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
            placeholder="搜索情报、对象、假设和证据"
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
            <Route path="/" element={<IntelligenceFlowPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/youtube" element={<YouTubeHubPage />} />
            <Route path="/youtube/subscriptions" element={<SubscriptionPage />} />
            <Route path="/youtube/summary/:documentId" element={<VideoSummaryPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/reader" element={<ReaderPage />} />
            <Route path="/reader/:documentId" element={<ReaderPage />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/provenance" element={<ProvenanceGraphPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/entity" element={<EntityPage />} />
            <Route path="/entity/:entityId" element={<EntityPage />} />
            <Route path="/investment" element={<InvestmentDashboardPage />} />
            {/* Task 9 replaces this compatibility target with account discovery. */}
            <Route path="/investment/accounts" element={<InvestmentSourcesPage />} />
            <Route path="/investment/edge" element={<InformationEdgePage />} />
            <Route path="/investment/themes" element={<InvestmentThemesPage />} />
            <Route path="/investment/watchlist" element={<InvestmentWatchlistPage />} />
            <Route path="/investment/items" element={<InvestmentItemsPage />} />
            <Route path="/investment/sources" element={<InvestmentSourcesPage />} />
            <Route path="/investment/claims" element={<InvestmentClaimsPage />} />
            <Route path="/investment/theses" element={<InvestmentThesesPage />} />
            <Route path="/investment/calendar" element={<InvestmentCalendarPage />} />
            <Route path="/investment/digest" element={<InvestmentDigestPage />} />
            <Route path="/notebooklm" element={<NotebookPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/settings/models" element={<ModelManagementPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
    <CompanionDrawer />
    </CompanionProvider>
    </ConfigProvider>
  );
}
