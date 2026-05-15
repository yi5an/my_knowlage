import { apiRequest } from "./client";

export type SearchAnswer = {
  answer: string;
  citations: Array<{ source: string; quote: string }>;
};

export const searchApi = {
  ask(query: string) {
    return apiRequest<SearchAnswer>("/search", { method: "POST", body: { query } });
  },
};

