import { apiRequest } from "./client";
import type {
  CompanionContext,
  CompanionMessage,
  CompanionSession,
  CompanionSessionDetail,
} from "../types/companion";

export const companionApi = {
  createOrReuseSession(context: CompanionContext) {
    return apiRequest<CompanionSession>("/companion/sessions", {
      method: "POST",
      body: {
        workspace_id: context.workspaceId,
        subject_type: context.subjectType,
        subject_id: context.subjectId,
      },
    });
  },
  getSession(sessionId: string) {
    return apiRequest<CompanionSessionDetail>(`/companion/sessions/${sessionId}`);
  },
  sendMessage(sessionId: string, content: string) {
    return apiRequest<CompanionMessage>(`/companion/sessions/${sessionId}/messages`, {
      method: "POST",
      body: { content },
    });
  },
  triggerInsights(sessionId: string) {
    return apiRequest<{ task_job_id: string; status: string }>(
      `/companion/sessions/${sessionId}/insights`,
      { method: "POST" },
    );
  },
};
