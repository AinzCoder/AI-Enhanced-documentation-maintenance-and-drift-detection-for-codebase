export interface ApiErrorResponse {
  detail?: string | Record<string, unknown> | unknown[];
  message?: string;
  error?: string;
}

export interface ApiHealthResponse {
  message: string;
}

export interface AnalyzeRequest {
  repository_path: string;
  mode?: AnalysisMode;
  base_commit?: string | null;
}

export type AnalysisMode = "full" | "working_tree" | "commits";

export interface AnalysisError {
  stage: string;
  file?: string | null;
  message: string;
}

export interface CodeChange {
  type?: string;
  class?: string;
  method?: string;
  source_file?: string;
  method_signature?: string;
  parameter_types?: string[];
  start_line?: number;
  end_line?: number;
  old_start_line?: number;
  old_end_line?: number;
  [key: string]: unknown;
}

export interface DriftFinding {
  type?: string;
  finding_type?: string;
  class?: string;
  method?: string;
  reason?: string;
  change_type?: string;
  review_classification?: string;
  documentation_target?: string | null;
  documentation_file?: string;
  source_file?: string;
  evidence?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AnalyzeFileResult {
  file: string;
  changes: CodeChange[];
  documentation_files: string[];
  drift: DriftFinding[];
  change_type: string;
  git_change_type: string;
  old_file: string | null;
  new_file: string | null;
  errors?: AnalysisError[];
}

export interface AnalyzeResponse {
  repository: string;
  current_commit: string | null;
  previous_commit: string | null;
  results: AnalyzeFileResult[];
  mode: "working_tree" | "commits";
}

export interface MethodAnalysis {
  name: string;
  signature: string;
  return_type: string | null;
  parameters: Array<{ name: string; type: string | null }>;
  body_available: boolean;
  body_preview: string | null;
  comment: string | null;
  start_line: number | null;
  end_line: number | null;
}

export interface ClassAnalysis {
  name: string;
  comment: string | null;
  method_count: number;
  methods: MethodAnalysis[];
}

export interface FullAnalysisFile {
  file: string;
  package: string | null;
  line_count: number | null;
  class_count: number;
  method_count: number;
  classes: ClassAnalysis[];
}

export interface FullAnalysisSummary {
  java_file_count: number;
  files_analyzed: number;
  files_with_errors: number;
  class_count: number;
  method_count: number;
  total_java_source_lines: number;
  line_count_unavailable: number;
}

export interface CoverageSummary {
  java_file_count: number;
  class_count: number;
  method_count: number;
  documented_class_count: number;
  missing_class_count: number;
  ambiguous_class_count: number;
  unsupported_class_count: number;
  documented_method_count: number;
  missing_method_count: number;
  ambiguous_method_count: number;
  unsupported_method_count: number;
  documentation_file_count: number;
  empty_documentation_file_count: number;
}

export interface DocumentationFinding {
  finding_type: string;
  source_file?: string | null;
  documentation_file?: string | null;
  class?: string | null;
  method?: string | null;
  signature?: string | null;
  documentation_target?: string | null;
  reason?: string | null;
  review_classification?: string;
  evidence?: Record<string, unknown>;
  source_line_range?: {
    start_line?: number;
    end_line?: number;
  };
  [key: string]: unknown;
}

export interface ClassCoverage {
  source_file: string;
  class: string;
  package?: string | null;
  coverage: string;
  documentation_file?: string | null;
  methods: Array<{
    method: string;
    signature: string;
    coverage: string;
    documentation_file?: string | null;
    [key: string]: unknown;
  }>;
  [key: string]: unknown;
}

export interface DocumentationAnalysis {
  summary: CoverageSummary;
  classes: ClassCoverage[];
  covered_classes: unknown[];
  covered_methods: unknown[];
  missing_documentation_findings: DocumentationFinding[];
  empty_documentation_findings: DocumentationFinding[];
  ambiguous_mappings: DocumentationFinding[];
  proposed_documentation_targets: string[];
  findings: DocumentationFinding[];
  errors: AnalysisError[];
}

export interface FullAnalyzeResponse {
  repository: string;
  analysis_mode: "full";
  summary: FullAnalysisSummary;
  files: FullAnalysisFile[];
  documentation_files: string[];
  documentation_analysis: DocumentationAnalysis;
  errors: AnalysisError[];
}

export interface FullDocumentationRequest {
  repository_path: string;
  target_documentation_file?: string | null;
  include_repository_overview?: boolean;
  max_methods?: number | null;
}

export type GenerationStatus = "complete" | "partial" | "failed";
export type ApprovalStatus =
  | "pending"
  | "processing"
  | "approved"
  | "rejected"
  | "stale"
  | "failed"
  | "unavailable";

export interface GeneratedClass {
  source_file: string;
  package?: string | null;
  class: string;
  identity: string;
  description: string;
  start_line: number;
  end_line: number;
  source_context_complete?: boolean;
}

export interface GeneratedMethod {
  source_file: string;
  package?: string | null;
  class: string;
  signature: string;
  method: string;
  documentation: string;
  start_line: number;
  end_line: number;
  source_context_complete: boolean;
}

export interface RetrievalSummary {
  strategy?: string;
  vector_store_used?: boolean;
  repository_scoped?: boolean;
  fallback_used?: boolean;
  fallback_count?: number;
  query_count?: number;
  retrieved_chunks?: number;
  indexing?: DocumentationIndexingSummary | null;
  errors?: AnalysisError[];
}

export interface DocumentationIndexingSummary {
  indexed_files: number;
  skipped_files: number;
  deleted_files: number;
  indexed_chunks: number;
  error_count: number;
}

export interface FullDocumentationResponse {
  repository: string;
  documentation_target: string;
  generated_markdown: string | null;
  generated_classes: GeneratedClass[];
  generated_methods: GeneratedMethod[];
  skipped_documented_methods: Array<{
    source_file: string;
    class: string;
    signature: string;
    documentation_file?: string | null;
  }>;
  repository_overview: string | null;
  errors: AnalysisError[];
  generation_status: GenerationStatus;
  source_hashes: Record<string, string>;
  target_hash_at_generation: string;
  ambiguous_documentation_mappings: DocumentationFinding[];
  retrieval?: RetrievalSummary;
  context_limits?: Record<string, number>;
  generation_id: string | null;
  approval_status: ApprovalStatus;
}

export interface GenerationAudit {
  event_type: string;
  generation_id: string;
  repository: string;
  repository_identity: string;
  documentation_target: string;
  status: ApprovalStatus;
  timestamp: string;
  source_hashes: Record<string, string>;
  documentation_hash_before: string;
  documentation_hash_after: string;
  generated_classes: Array<{
    source_file?: string;
    class?: string;
    identity?: string;
  }>;
  generated_methods: Array<{
    source_file?: string;
    class?: string;
    signature?: string;
  }>;
  failure_reason: string | null;
}

export interface GenerationRecord {
  generation_id: string;
  repository: string;
  repository_identity: string;
  documentation_target: string;
  generated_markdown: string;
  generated_classes: GeneratedClass[];
  generated_methods: GeneratedMethod[];
  repository_overview: string | null;
  ambiguous_documentation_mappings: DocumentationFinding[];
  generation_status: GenerationStatus;
  created_at: string;
  updated_at?: string;
  source_hashes: Record<string, string>;
  target_hash_before: string;
  status: ApprovalStatus;
  failure_reason?: string | null;
  audit?: GenerationAudit;
}

export interface GenerationDecisionRequest {
  decision: "approve" | "reject";
}

export interface ApprovalResponse {
  generation_id: string;
  status: ApprovalStatus;
  generation_status?: GenerationStatus;
  documentation_target: string;
  audit?: GenerationAudit;
}

export interface SuggestionRequest {
  repository_path: string;
  file_path: string;
  class_name: string;
  method_name: string;
  change_type: string;
}

export interface RetrievedDocumentMetadata {
  repository_id?: string;
  documentation_file: string;
  section_heading: string;
  chunk_index: number;
  content_hash: string;
  source_type: string;
  [key: string]: string | number | undefined;
}

export interface SuggestionResponse {
  class: string;
  method: string;
  change_type: string;
  target_documentation: string | null;
  retrieved_documents: RetrievedDocumentMetadata[];
  suggestion: string;
  developer_comment: string | null;
  rag_retrieval?: {
    repository_scoped: boolean;
    repository_id: string | null;
    vector_store_used: boolean;
    fallback_used: boolean;
    fallback_strategy?: string | null;
    available: boolean;
    error?: string | null;
    indexing?: unknown;
  };
}

export interface SuggestionErrorResponse {
  error: string;
}

export interface RagIndexRequest {
  repository_path: string;
}

export interface RagIndexError {
  file: string | null;
  stage: string;
  message: string;
}

export interface RagIndexResponse {
  repository: string;
  repository_id: string;
  indexed_files: string[];
  skipped_files: string[];
  deleted_files: string[];
  indexed_chunks: number;
  errors: RagIndexError[];
}

export interface RagStatusResponse {
  repository: string;
  repository_id: string;
  index_available: boolean;
  indexed_document_count: number | null;
  chunk_count: number | null;
  last_successful_indexing: string | null;
}
