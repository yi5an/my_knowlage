import type {
  CreateSourcePayload,
  InfoLayer,
  SourceType,
} from "../../services/investmentApi";

export const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  rss: "RSS / Atom",
  x_rss: "X / RSSHub",
  x_nitter: "X / Nitter",
  x_brightdata: "X / Bright Data",
  x_web: "X / 网页采集",
  sec_edgar: "SEC EDGAR",
  federal_reserve_rss: "美联储 RSS",
  bls: "BLS",
  fred: "FRED",
  hkex: "港交所 HKEX",
  cninfo: "巨潮 CNINFO",
  manual: "手动",
};

export class SourcePayloadError extends Error {}

export interface SourceDraftValues {
  source_type: SourceType;
  name: string;
  url?: string;
  cik?: string;
  series?: string | string[];
  years?: number;
  limit?: number;
  profile_urls?: string | string[];
  x_web_mode?: "account" | "keyword";
  x_username?: string;
  x_keyword?: string;
  x_target?: string;
  x_base_url?: string;
  default_info_layer?: InfoLayer;
  default_watchlist_ids?: string[];
  poll_interval_seconds?: number;
}

function optionalText(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const text = value.trim();
  return text || undefined;
}

function required(value: unknown, message: string): string {
  const text = optionalText(value);
  if (!text) throw new SourcePayloadError(message);
  return text;
}

function splitValues(raw: string | string[] | undefined): string[] {
  if (Array.isArray(raw)) return raw.map((value) => value.trim()).filter(Boolean);
  if (typeof raw !== "string") return [];
  return raw
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function defaultLayer(sourceType: SourceType): InfoLayer {
  return sourceType === "x_rss" ||
    sourceType === "x_nitter" ||
    sourceType === "x_brightdata" ||
    sourceType === "x_web"
    ? "opinion"
    : "news";
}

function defaultPollInterval(sourceType: SourceType): number {
  if (sourceType === "x_brightdata") return 21600;
  if (sourceType === "x_web") return 900;
  return 3600;
}

function urlRequiredMessage(sourceType: SourceType): string {
  if (sourceType === "rss") return "RSS / Atom 需要填写 URL";
  return `${SOURCE_TYPE_LABEL[sourceType]} 需要填写 URL`;
}

export function buildSourcePayload(values: SourceDraftValues): CreateSourcePayload {
  const sourceType = values.source_type;
  const payload: CreateSourcePayload = {
    source_type: sourceType,
    name: required(values.name, "数据源需要填写名称"),
    default_info_layer: values.default_info_layer ?? defaultLayer(sourceType),
    default_watchlist_ids: values.default_watchlist_ids ?? [],
    poll_interval_seconds: values.poll_interval_seconds ?? defaultPollInterval(sourceType),
  };

  if (sourceType === "sec_edgar") {
    payload.config = {
      cik: required(values.cik, "SEC EDGAR 需要填写 CIK"),
      forms: ["10-K", "10-Q", "8-K", "4"],
    };
    return payload;
  }

  if (sourceType === "bls" || sourceType === "fred") {
    const series = splitValues(values.series);
    if (series.length === 0) {
      throw new SourcePayloadError(
        sourceType === "bls" ? "BLS 需要填写至少一个序列 ID" : "FRED 需要填写至少一个序列 ID",
      );
    }
    payload.config =
      sourceType === "bls"
        ? { series, years: values.years ?? 1 }
        : { series, limit: values.limit ?? 5 };
    return payload;
  }

  if (sourceType === "x_brightdata") {
    const profileUrls = splitValues(values.profile_urls);
    if (profileUrls.length === 0) {
      throw new SourcePayloadError("X / Bright Data 需要填写至少一个账号 URL");
    }
    payload.config = {
      profile_urls: profileUrls.map((value) =>
        value.startsWith("http") ? value : `https://x.com/${value.replace(/^@/, "")}`,
      ),
    };
    return payload;
  }

  if (sourceType === "x_web") {
    const mode = values.x_web_mode === "keyword" ? "keyword" : "account";
    payload.config =
      mode === "keyword"
        ? {
            mode,
            query: required(values.x_keyword, "X 关键词采集需要填写关键词"),
            max_items_per_poll: 50,
          }
        : {
            mode,
            username: required(values.x_username, "X 网页采集需要填写 X 用户名").replace(/^@/, ""),
            max_items_per_poll: 50,
          };
    return payload;
  }

  if (sourceType === "x_rss" || sourceType === "x_nitter") {
    const target = required(values.x_target, `${SOURCE_TYPE_LABEL[sourceType]} 需要填写用户名或 Feed URL`);
    if (/^https?:\/\//i.test(target)) {
      payload.url = target;
      return payload;
    }
    payload.config = {
      username: target.replace(/^@/, ""),
      ...(sourceType === "x_rss"
        ? { rsshub_base_url: optionalText(values.x_base_url) ?? "https://rsshub.app" }
        : { nitter_base_url: optionalText(values.x_base_url) ?? "https://nitter.net" }),
    };
    return payload;
  }

  payload.url = required(values.url, urlRequiredMessage(sourceType));
  return payload;
}
