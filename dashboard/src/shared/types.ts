export type JobStatus =
  | "queued"
  | "running"
  | "collecting_results"
  | "restoring"
  | "completed"
  | "completed_with_failure"
  | "restore_failed";

export type NavKey = "overview" | "issues" | "ue-flow" | "protocol-replay" | "reports";

export interface JobEvent {
  time: string;
  label: string;
}

export interface JobSummary {
  id: string;
  type: "issue_dry_run" | "issue_live_run" | "restore" | "ue_flow";
  status: JobStatus;
  mutating: boolean;
  title: string;
  startedAt: string;
  finishedAt?: string;
  stepIndex: number;
  stepTotal: number;
  stepName: string;
  progressLabel: string;
  elapsedSeconds: number;
  stageElapsedSeconds: number;
  stdoutTail: string[];
  stderrTail: string[];
  events: JobEvent[];
  resultPath?: string;
  resultSummary?: Record<string, unknown>;
  error?: string;
  lastLogAt?: string;
  idleSeconds?: number;
  abortable?: boolean;
}

export interface ContainerState {
  name: string;
  status: string;
  running: boolean;
  exitCode: number | null;
}

export interface SystemStatus {
  checkedAt: string;
  baseline: {
    ready: boolean;
    summary: string;
    stdout: string[];
    stderr: string[];
    exitCode: number;
  };
  open5gsImage: string;
  branch: string;
  lastRestoreState: "unknown" | "ok" | "failed";
  containers: ContainerState[];
  currentMutatingJob?: JobSummary | null;
}

export interface IssueRunInfo {
  path: string;
  mode: string;
  classification?: string;
  baselineRestored: boolean;
  generatedAt?: string;
  result: Record<string, unknown>;
}

export interface IssueCaseSummary {
  id: string;
  title: string;
  component: string;
  protocol: string;
  issue: string;
  fix: string;
  casePath: string;
  resultPath?: string;
  classification?: string;
  baselineRestored?: boolean;
  displayMode?: string;
  latestLiveRun?: IssueRunInfo;
  latestDryRun?: IssueRunInfo;
  summary: {
    mutation: string;
    request: string;
  };
  result?: Record<string, unknown>;
  caseData: Record<string, unknown>;
}

export interface FlowSummary {
  flow: string;
  label: string;
  status: "present" | "missing";
  result?: string;
  runId?: string;
  generatedAt?: string;
  resultPath?: string;
  artifacts?: Record<string, string>;
  counts?: Record<string, number>;
  timeline?: Array<Record<string, unknown>>;
  checks?: Array<Record<string, unknown>>;
}

export interface ReportItem {
  slug: string;
  title: string;
  path: string;
  kind: "report" | "doc";
}

export interface MarkdownDocument {
  slug: string;
  title: string;
  path: string;
  content: string;
}

export interface FileDocument {
  path: string;
  content: string;
}

export interface ProtocolReplayCard {
  id: string;
  title: string;
  description: string;
  requirement: string;
  path: string;
}
