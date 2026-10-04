export interface Finding {
  title: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  confidence: "high" | "medium" | "low";
  evidence: string;
  analysis: string;
}

export interface LedgerEntry {
  timestamp: string;
  run_id: string;
  mission: string;
  finding_count: number;
  severity_counts: Record<string, number>;
  new_count: number;
  resolved_count: number;
  persistent_count: number;
  posture_score: number;
  trend: "improving" | "stable" | "degrading";
  prev_score: number;
  new_findings: string[];
  resolved_findings: string[];
  cost: number;
  total_runs: number;
  signature?: string;
}

export interface Report {
  id: string;
  run_id: string;
  mission: string;
  objective: string;
  timestamp: string;
  finding_count: number;
  findings: Finding[];
  summary: string;
  verification: Record<string, unknown>;
  budget: Record<string, unknown>;
  signed: boolean;
}

export interface DaemonState {
  type: "state";
  repo: string;
  repo_name: string;
  posture: number | null;
  trend: string | null;
  finding_count: number;
  hardening_runs: number;
  report_count: number;
  ledger: LedgerEntry[];
  running: string | null;
  event_buffer: PipelineEvent[];
}

export interface PipelineEvent {
  event_type: string;
  agent_id: string;
  timestamp: string;
  payload: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  run_id?: string;
  action_id?: string;
  _daemon_ts?: string;
}

export interface TrustData {
  type: "trust";
  signing_available: boolean;
  public_key: string | null;
  public_key_short: string | null;
  key_algorithm: string | null;
  key_path: string | null;
  hardware_signing_available: boolean;
  signed_events: number;
  unsigned_events: number;
  signed_reports: number;
  latest_signature: string | null;
}

export interface VerificationResult {
  type: "verification";
  report_id: string;
  valid: boolean;
  public_key?: string;
  error?: string;
}

export const SEV_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#3b82f6",
  info: "#6b7280",
};

export const AGENT_COLORS: Record<string, string> = {
  system: "#78716c",
  controller: "#d97706",
  planner: "#f59e0b",
  implementer: "#eab308",
  debugger: "#ef4444",
  security: "#10b981",
  release: "#06b6d4",
  archivist: "#a855f7",
  testgen: "#14b8a6",
};
