export interface AnalysisResult {
  threat_score: number;
  primary_intent: string;
  detected_patterns: string[];
  analysis_summary: string;
  stoic_nudge: string;
  suggested_action: string;
  /** Structured record of every code execution step the model ran. */
  code_execution_steps?: CodeExecutionStep[];
  /** @deprecated use code_execution_steps instead */
  code_execution_output?: string[];
}

/** A bash (shell) code execution step. */
export interface BashStep {
  type: "bash";
  stdout: string;
  stderr: string;
  return_code: number;
  /** File IDs of any files produced (e.g. plots, CSVs). */
  output_file_ids?: string[];
  /** Present when the tool itself failed before running code. */
  error_code?: string;
}

/** A text-editor code execution step (view / create / str_replace). */
export interface EditorStep {
  type: "editor";
  operation: "view" | "create" | "str_replace" | "error" | "unknown";
  /** File contents returned by a view operation. */
  file_content?: string;
  file_type?: "text" | "image" | "pdf";
  /** Start line numbers from a str_replace operation. */
  old_start?: number | null;
  new_start?: number | null;
  error_code?: string;
}

export type CodeExecutionStep = BashStep | EditorStep;

export interface AnalysisOptions {
  message: string;
  stream?: boolean;
}
