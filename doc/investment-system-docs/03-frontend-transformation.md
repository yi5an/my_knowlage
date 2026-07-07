# 前端改造文档

日期：2026-07-02  
技术栈：React 18、Vite、TypeScript、Ant Design 5、react-router-dom

## 1. 改造目标

在现有前端中新增投资信息系统入口，不重做应用壳层。

现有入口在：

```text
frontend/src/App.tsx
```

需要新增：

```text
/investment
/investment/watchlist
/investment/items
/investment/claims
/investment/theses
/investment/sources
/investment/calendar
/investment/digest
```

第一阶段实现前五个路由，第二阶段实现后三个路由。

## 2. 新增文件

```text
frontend/src/services/investmentApi.ts
frontend/src/pages/InvestmentDashboardPage.tsx
frontend/src/pages/InvestmentWatchlistPage.tsx
frontend/src/pages/InvestmentItemsPage.tsx
frontend/src/pages/InvestmentClaimsPage.tsx
frontend/src/pages/InvestmentThesesPage.tsx
frontend/src/pages/InvestmentSourcesPage.tsx
frontend/src/pages/InvestmentCalendarPage.tsx
frontend/src/pages/InvestmentDigestPage.tsx
frontend/src/components/investment/InfoLayerTag.tsx
frontend/src/components/investment/ImpactTag.tsx
frontend/src/components/investment/ReviewStatusTag.tsx
frontend/src/components/investment/InvestmentItemDrawer.tsx
frontend/src/components/investment/WatchlistSelector.tsx
```

## 3. App.tsx 改造

新增图标：

```tsx
import { FundProjectionScreenOutlined } from "@ant-design/icons";
```

新增 nav item：

```tsx
{ key: "/investment", icon: <FundProjectionScreenOutlined />, label: <Link to="/investment">投资工作台</Link> },
```

新增 routes：

```tsx
<Route path="/investment" element={<InvestmentDashboardPage />} />
<Route path="/investment/watchlist" element={<InvestmentWatchlistPage />} />
<Route path="/investment/items" element={<InvestmentItemsPage />} />
<Route path="/investment/claims" element={<InvestmentClaimsPage />} />
<Route path="/investment/theses" element={<InvestmentThesesPage />} />
<Route path="/investment/sources" element={<InvestmentSourcesPage />} />
<Route path="/investment/calendar" element={<InvestmentCalendarPage />} />
<Route path="/investment/digest" element={<InvestmentDigestPage />} />
```

## 4. investmentApi.ts

放在：

```text
frontend/src/services/investmentApi.ts
```

复用现有：

```text
frontend/src/services/client.ts
```

类型定义：

```ts
export type InfoLayer = "primary_source" | "macro_calendar" | "news" | "opinion";
export type SourceCredibility = "official" | "reliable_media" | "personal_opinion" | "unverified";
export type ImpactDirection = "positive" | "negative" | "neutral" | "uncertain";
export type ImpactHorizon = "short" | "mid" | "long" | "unknown";
export type ActionStatus = "pending_review" | "tracking" | "ignored" | "researched" | "archived";

export interface InvestmentItem {
  id: string;
  workspace_id: string;
  document_id?: string | null;
  title: string;
  source_url?: string | null;
  source_name?: string | null;
  info_layer: InfoLayer;
  source_credibility: SourceCredibility;
  published_at?: string | null;
  event_at?: string | null;
  summary?: string | null;
  importance: "low" | "medium" | "high";
  impact_direction: ImpactDirection;
  impact_horizon: ImpactHorizon;
  thesis_impact: "supports" | "weakens" | "contradicts" | "unrelated" | "unknown";
  action_status: ActionStatus;
  review_at?: string | null;
}
```

API 函数：

```ts
export async function getInvestmentDashboard(workspaceId = "ws_default") {}
export async function listInvestmentItems(params: ListInvestmentItemsParams) {}
export async function createInvestmentItem(payload: CreateInvestmentItemPayload) {}
export async function updateInvestmentItem(id: string, payload: UpdateInvestmentItemPayload) {}
export async function listWatchlist(workspaceId = "ws_default") {}
export async function createWatchlistItem(payload: CreateWatchlistPayload) {}
export async function listClaims(params: ListClaimsParams) {}
export async function createClaim(payload: CreateClaimPayload) {}
export async function verifyClaim(id: string) {}
export async function listTheses(params: ListThesesParams) {}
export async function createThesis(payload: CreateThesisPayload) {}
export async function listSources(workspaceId = "ws_default") {}
export async function pollSource(id: string) {}
```

## 5. 投资工作台页面

文件：

```text
frontend/src/pages/InvestmentDashboardPage.tsx
```

布局：

```text
PageHeader
  - title: 投资工作台
  - actions: 添加信息、添加观察对象、添加数据源

Metric Row
  - 今日待处理
  - 待验证观点
  - 假设被挑战
  - 今日新增一手信息

Main Grid
  - 今日待处理信息 Table
  - 待验证观点 List
  - 最近一手信息 List
  - 宏观事件 Timeline
```

不要做营销式大 Hero。它是工作台，需要密集、可扫描、可操作。

## 6. 投资信息列表

文件：

```text
frontend/src/pages/InvestmentItemsPage.tsx
```

功能：

1. 筛选层级：全部、一手、宏观、新闻、观点。
2. 筛选状态：待审阅、跟踪中、已研究、忽略。
3. 搜索标题和来源。
4. 表格列：
   - 标题
   - 层级
   - 来源
   - 发布时间
   - 重要性
   - 影响方向
   - 影响周期
   - 处理状态
   - 操作
5. 点击行打开 `InvestmentItemDrawer`。

## 7. 数据源页面

文件：

```text
frontend/src/pages/InvestmentSourcesPage.tsx
```

第二阶段实现。

表格列：

```text
名称
类型
默认层级
抓取频率
上次抓取
下次抓取
最近错误
启用状态
操作
```

操作：

```text
新增
编辑
启用/停用
立即抓取
查看最近任务
```

新增表单支持：

```text
RSS
SEC 公司 filings
Federal Reserve RSS
BLS series
FRED series
HKEX search URL
CNINFO URL / authorized API
```

## 8. YouTube 页面改造

文件：

```text
frontend/src/pages/YouTubeHubPage.tsx
frontend/src/pages/VideoSummaryPage.tsx
```

改造：

1. 视频总结列表卡片显示 `观点解读` 标签。
2. 视频总结详情页增加按钮：`提取为待验证观点`。
3. 弹窗字段：
   - 观点内容
   - 关联观察对象
   - 关联投资假设
   - 需要验证的事实
4. 提交到：

```text
POST /api/v1/investment/claims
```

## 9. 前端状态与错误

所有真实数据源错误必须显示，不允许静默变成空列表。

错误提示：

```text
数据源未配置
源站请求超时
源站限流，请稍后重试
解析失败，请检查数据源配置
```

## 10. 前端测试

新增测试：

```text
frontend/src/pages/InvestmentDashboardPage.test.tsx
frontend/src/pages/InvestmentItemsPage.test.tsx
frontend/src/pages/InvestmentSourcesPage.test.tsx
```

测试重点：

1. 空状态显示真实提示。
2. API 返回错误时显示错误信息。
3. 筛选层级后调用正确参数。
4. 点击“立即抓取”调用 `pollSource`。

运行：

```bash
cd frontend
npm run lint
npm run test
npm run build
```

