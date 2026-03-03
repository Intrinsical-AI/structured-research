// AUTO-GENERATED FILE. DO NOT EDIT.
// Source: docs/openapi_v1.json

export type BundleWriteResponse = {
  "ok": boolean;
  "version"?: string | null;
  "errors"?: ValidationIssue[];
}

export type CvCandidateInput = {
  "id"?: string | null;
  "name"?: string | null;
  "seniority": string;
  "tech_stack"?: CvSkillSetInput | null;
  "experience"?: CvExperienceInput[];
  "education"?: string[];
  "spoken_languages"?: string[];
  "location"?: string | null;
  "timezone"?: string | null;
  "availability_days"?: number | null;
  "role_focus"?: string[];
}

export type CvExperienceInput = {
  "company": string;
  "title": string;
  "duration_months"?: number | null;
  "highlights"?: string[];
  "stack"?: string[];
}

export type CvSkillSetInput = {
  "languages"?: string[];
  "frameworks"?: string[];
  "platforms"?: string[];
  "domains"?: string[];
}

export type GenCVRequest = {
  "profile_id": string;
  "job": Record<string, unknown>;
  "candidate_profile": CvCandidateInput;
  "selected_claim_ids"?: string[] | null;
  "llm_model"?: string | null;
  "allow_mock_fallback"?: boolean;
}

export type GenCVResponse = {
  "cv_markdown": string;
  "generated_cv_json"?: Record<string, unknown> | null;
  "model_info"?: Record<string, unknown> | null;
}

export type HTTPValidationError = {
  "detail"?: ValidationError[];
}

export type IngestError = {
  "line_no": number;
  "raw_preview": string;
  "kind": "json_parse" | "not_object" | "schema_validation";
  "message": string;
}

export type JsonlInvalidRecord = {
  "line": number;
  "error": string;
  "raw": string;
  "kind": "json_parse" | "not_object" | "schema_validation";
}

export type JsonlValidateMetrics = {
  "total_lines": number;
  "json_valid_lines": number;
  "schema_valid_records": number;
  "invalid_lines": number;
}

export type JsonlValidateRequest = {
  "profile_id": string;
  "raw_jsonl": string;
}

export type JsonlValidateResponse = {
  "valid_records": Record<string, unknown>[];
  "invalid_records": JsonlInvalidRecord[];
  "metrics": JsonlValidateMetrics;
}

export type ProfileBundle = {
  "task_id"?: string;
  "profile_id": string;
  "constraints": Record<string, unknown>;
  "task": Record<string, unknown>;
  "task_config": Record<string, unknown>;
  "user_profile"?: Record<string, unknown> | null;
  "domain_schema"?: Record<string, unknown> | null;
  "result_schema"?: Record<string, unknown> | null;
}

export type ProfileSummary = {
  "id": string;
  "name": string;
  "updated_at": string;
}

export type PromptGenerateRequest = {
  "profile_id": string;
  "step"?: string;
}

export type PromptGenerateResponse = {
  "profile_id": string;
  "step": string;
  "prompt": string;
  "constraints_embedded": boolean;
  "prompt_hash": string;
}

export type RunResponseMetrics = {
  "loaded": number;
  "processed": number;
  "skipped": number;
  "gate_passed": number;
  "gate_failed": number;
  "gate_pass_rate": number;
  "started_at": string;
  "finished_at": string;
}

export type RunScoreRequest = {
  "profile_id": string;
  "records": Record<string, unknown>[];
  "require_snapshot"?: boolean;
}

export type RunScoreResponse = {
  "run_id": string;
  "profile_id": string;
  "scored_records": Record<string, unknown>[];
  "metrics": RunResponseMetrics;
  "errors": Record<string, unknown>[];
  "snapshot_dir"?: string | null;
  "snapshot_status"?: "written" | "failed";
  "snapshot_error"?: string | null;
}

export type RunValidateChecks = {
  "profile_exists": boolean;
  "constraints_valid": boolean;
  "scoring_config_valid": boolean;
  "all_records_schema_valid": boolean;
  "snapshot_io_checked"?: boolean;
  "snapshot_io_writable"?: boolean | null;
}

export type RunValidateSummary = {
  "ok": boolean;
  "profile_id": string;
  "total_records": number;
  "valid_records": number;
  "invalid_records": number;
  "errors": IngestError[];
  "checks": RunValidateChecks;
  "snapshot_probe_dir"?: string | null;
  "snapshot_probe_error"?: string | null;
}

export type TaskSummary = {
  "task_id": string;
  "name": string;
  "capabilities"?: string[];
}

export type ValidationError = {
  "loc": (string | number)[];
  "msg": string;
  "type": string;
  "input"?: unknown;
  "ctx"?: Record<string, unknown>;
}

export type ValidationIssue = {
  "path": string;
  "code": string;
  "message": string;
  "severity"?: "error" | "warning";
}
