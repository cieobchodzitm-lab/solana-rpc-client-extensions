export interface AnalysisResult {
  threat_score: number;
  primary_intent: string;
  detected_patterns: string[];
  analysis_summary: string;
  stoic_nudge: string;
  suggested_action: string;
}

export interface AnalysisOptions {
  message: string;
  stream?: boolean;
}
