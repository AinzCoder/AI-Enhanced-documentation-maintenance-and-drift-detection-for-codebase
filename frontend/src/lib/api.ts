import axios from "axios";
import { apiBaseUrl } from "@/lib/apiBaseUrl";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ApiErrorResponse,
  ApiHealthResponse,
  ApprovalResponse,
  FullDocumentationRequest,
  FullDocumentationResponse,
  FullAnalyzeResponse,
  GenerationDecisionRequest,
  GenerationRecord,
  RagIndexRequest,
  RagIndexResponse,
  RagStatusResponse,
  SuggestionErrorResponse,
  SuggestionRequest,
  SuggestionResponse,
} from "@/types/api";

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 15_000,
});

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiErrorResponse>(error)) {
    const responseData = error.response?.data;
    if (typeof responseData?.detail === "string") {
      return responseData.detail;
    }
    if (Array.isArray(responseData?.detail)) {
      const validationMessages = responseData.detail
        .map((item) => {
          if (typeof item !== "object" || item === null || !("msg" in item)) {
            return null;
          }
          const message = item.msg;
          if (typeof message !== "string") {
            return null;
          }
          const location =
            "loc" in item && Array.isArray(item.loc)
              ? item.loc.filter(
                  (part): part is string | number =>
                    typeof part === "string" || typeof part === "number"
                )
              : [];
          return location.length > 0
            ? `${location.join(".")}: ${message}`
            : message;
        })
        .filter((message): message is string => message !== null);
      if (validationMessages.length > 0) {
        return validationMessages.join(" ");
      }
    }
    if (typeof responseData?.message === "string") {
      return responseData.message;
    }
    if (typeof responseData?.error === "string") {
      return responseData.error;
    }
    if (error.code === "ECONNABORTED") {
      return "The backend request timed out. Try again when the service is available.";
    }
    if (!error.response) {
      return "Could not connect to the DocGuard backend. Check that FastAPI is running.";
    }
    return `The backend returned an unexpected response (${error.response.status}).`;
  }
  return "An unexpected error occurred while contacting the DocGuard backend.";
}

export async function checkBackendHealth(): Promise<ApiHealthResponse> {
  const { data } = await apiClient.get<ApiHealthResponse>("/");
  return data;
}

export async function analyzeRepository(
  request: AnalyzeRequest
): Promise<AnalyzeResponse> {
  const { data } = await apiClient.post<AnalyzeResponse>(
    "/analyze",
    request,
    { timeout: 120_000 }
  );
  return data;
}

export async function analyzeFullRepository(
  repositoryPath: string
): Promise<FullAnalyzeResponse> {
  const { data } = await apiClient.post<FullAnalyzeResponse>("/analyze/full", {
    repository_path: repositoryPath,
  }, { timeout: 120_000 });
  return data;
}

export async function generateFullDocumentation(
  request: FullDocumentationRequest,
  signal?: AbortSignal
): Promise<FullDocumentationResponse> {
  const { data } = await apiClient.post<FullDocumentationResponse>(
    "/documentation/generate/full",
    request,
    { timeout: 900_000, signal }
  );
  return data;
}

export async function getGeneration(
  generationId: string,
  signal?: AbortSignal
): Promise<GenerationRecord> {
  const { data } = await apiClient.get<GenerationRecord>(
    `/documentation/generation/${encodeURIComponent(generationId)}`,
    { signal }
  );
  return data;
}

export async function approveGeneration(
  generationId: string,
  request: GenerationDecisionRequest
): Promise<ApprovalResponse> {
  const { data } = await apiClient.post<ApprovalResponse>(
    `/documentation/generation/${encodeURIComponent(generationId)}/approve`,
    request,
    { timeout: 60_000 }
  );
  return data;
}

export async function rejectGeneration(
  generationId: string,
  request: GenerationDecisionRequest
): Promise<ApprovalResponse> {
  const { data } = await apiClient.post<ApprovalResponse>(
    `/documentation/generation/${encodeURIComponent(generationId)}/reject`,
    request,
    { timeout: 60_000 }
  );
  return data;
}

export async function indexRepository(
  request: RagIndexRequest,
  signal?: AbortSignal
): Promise<RagIndexResponse> {
  const { data } = await apiClient.post<RagIndexResponse>(
    "/rag/index",
    request,
    { timeout: 300_000, signal }
  );
  return data;
}

export async function getRagStatus(
  repositoryPath: string,
  signal?: AbortSignal
): Promise<RagStatusResponse> {
  const { data } = await apiClient.get<RagStatusResponse>("/rag/status", {
    params: { repository_path: repositoryPath },
    signal,
  });
  return data;
}

export async function suggestDocumentation(
  request: SuggestionRequest
): Promise<SuggestionResponse | SuggestionErrorResponse> {
  const { data } = await apiClient.post<
    SuggestionResponse | SuggestionErrorResponse
  >("/suggest", request);
  return data;
}
