export type ModelCapability = "llm" | "embedding" | "asr" | "ocr";
export type ProviderProtocol = "openai_compatible" | "glm_asr" | "knowpilot_ocr";

export type ModelProvider = {
  id: string;
  name: string;
  provider_type: ProviderProtocol;
  base_url: string | null;
  timeout_seconds: number;
  enabled: boolean;
  api_key_configured: boolean;
  api_key_hint: string | null;
  last_test_status: string | null;
  last_test_message: string | null;
  last_tested_at: string | null;
};

export type ManagedModel = {
  id: string;
  provider_id: string;
  model_name: string;
  model_type: ModelCapability;
  context_window: number | null;
  max_output_tokens: number | null;
  enabled: boolean;
};

export type ModelRoute = { capability: ModelCapability; model_config_id: string | null };
