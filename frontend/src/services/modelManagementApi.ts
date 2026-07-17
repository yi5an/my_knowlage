import { apiRequest } from "./client";
import type { ManagedModel, ModelCapability, ModelProvider, ModelRoute, ProviderProtocol } from "../types/modelManagement";

export const listProviders = () => apiRequest<ModelProvider[]>("/model-management/providers");
export const listModels = () => apiRequest<ManagedModel[]>("/model-management/models");
export const listRoutes = () => apiRequest<ModelRoute[]>("/model-management/routes");

export const createProvider = (body: { name: string; provider_type: ProviderProtocol; base_url?: string; api_key?: string; timeout_seconds: number }) =>
  apiRequest<ModelProvider>("/model-management/providers", { method: "POST", body });
export const createModel = (body: { provider_id: string; model_name: string; model_type: ModelCapability }) =>
  apiRequest<ManagedModel>("/model-management/models", { method: "POST", body });
export const saveRoute = (capability: ModelCapability, model_config_id: string) =>
  apiRequest<ModelRoute>(`/model-management/routes/${capability}`, { method: "PUT", body: { model_config_id } });
export const testProvider = (body: { provider_type: ProviderProtocol; base_url: string; api_key?: string; model_name: string; capability: ModelCapability; timeout_seconds: number }) =>
  apiRequest<{ status: string; message: string }>("/model-management/providers/test", { method: "POST", body });
