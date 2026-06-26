import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import type {
  EncodingTestcase,
  FileDocument,
  FlowSummary,
  IssueCaseSummary,
  JobSummary,
  MarkdownDocument,
  NavKey,
  ProtocolMessage,
  ProtocolMessagesResult,
  ProtocolReplayCard,
  ReplayValidationCase,
  ReplayValidationResult,
  ReportItem,
  SystemStatus
} from "../shared/types";

const navItems: Array<{ key: NavKey; label: string; description: string }> = [
  { key: "overview", label: "系统总览", description: "baseline 健康、容器状态、恢复入口" },
  { key: "protocol-replay", label: "协议 / 回放", description: "协议解析、编码与验证报告" },
  { key: "ue-flow", label: "UE 流程", description: "完整注册与释放流程结果" },
  { key: "issues", label: "Issue 测试", description: "Open5GS issue-driven testcase" }
  // { key: "reports", label: "报告", description: "进度、实施计划与阶段报告" }
];

const statusTone: Record<string, string> = {
  READY: "text-accent",
  PASS: "text-accent",
  completed: "text-accent",
  completed_with_failure: "text-warn",
  running: "text-warn",
  queued: "text-warn",
  restore_failed: "text-danger",
  FAIL: "text-danger",
  missing: "text-danger",
  DRY_RUN: "text-warn",
  VULNERABLE_CRASH: "text-danger",
  PFCP_ERROR_NO_IMPACT: "text-warn",
  NOT_REPRODUCED: "text-ink"
};

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({ error: response.statusText }))) as { error?: string };
    throw new Error(payload.error || response.statusText);
  }
  return (await response.json()) as T;
}

function classForStatus(status: string): string {
  return statusTone[status] ?? "text-ink";
}

function formatSeconds(value: number): string {
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatJobStatus(status: string): string {
  const labels: Record<string, string> = {
    queued: "排队中",
    running: "运行中",
    collecting_results: "收集结果中",
    restoring: "恢复 baseline 中",
    completed: "已完成",
    completed_with_failure: "已完成（含失败）",
    restore_failed: "恢复失败"
  };
  return labels[status] ?? status;
}

function pathTag(value?: string): JSX.Element {
  return <span className="font-mono text-xs text-muted break-all">{value ?? "无"}</span>;
}

function summarizeResultSummary(resultSummary: Record<string, unknown>): string {
  const parts: string[] = [];
  const classification = resultSummary.classification;
  const result = resultSummary.result;
  const request = resultSummary.request as { curl_exit_code?: number; curl_stderr?: string } | undefined;
  const before = resultSummary.target_before as { status?: string } | undefined;
  const after = resultSummary.target_after as { status?: string; exit_code?: number } | undefined;
  const restore = resultSummary.baseline_restore as { restored?: boolean } | undefined;

  if (typeof classification === "string") {
    parts.push(`classification=${classification}`);
  }
  if (typeof result === "string") {
    parts.push(`result=${result}`);
  }
  if (before?.status || after?.status) {
    parts.push(`target=${before?.status ?? "-"} -> ${after?.status ?? "-"}`);
  }
  if (typeof after?.exit_code === "number") {
    parts.push(`exit_code=${after.exit_code}`);
  }
  if (typeof request?.curl_exit_code === "number") {
    parts.push(`curl_exit=${request.curl_exit_code}`);
  }
  if (typeof restore?.restored === "boolean") {
    parts.push(`restored=${String(restore.restored)}`);
  }
  return parts.join("\n");
}

function SectionTitle(props: { title: string; description?: string; action?: JSX.Element }) {
  return (
    <div className="flex flex-col gap-3 border-b border-line pb-4 md:flex-row md:items-end md:justify-between">
      <div>
        <h2 className="text-xl font-semibold text-ink">{props.title}</h2>
        {props.description ? <p className="mt-1 text-sm text-muted">{props.description}</p> : null}
      </div>
      {props.action}
    </div>
  );
}

function ActionButton(props: {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "default" | "danger";
}) {
  const tone =
    props.tone === "danger"
      ? "border-danger/50 bg-danger/10 text-danger hover:bg-danger/15"
      : "border-line bg-panel text-ink hover:bg-[#16253a]";
  return (
    <button
      type="button"
      disabled={props.disabled}
      onClick={props.onClick}
      className={`rounded-xl border px-3 py-2 text-sm transition ${tone} disabled:cursor-not-allowed disabled:opacity-45`}
    >
      {props.label}
    </button>
  );
}

function SummaryCard(props: {
  title: string;
  value: string;
  detail?: string;
  tone?: string;
}) {
  return (
    <div className="min-w-0 overflow-hidden rounded-xl border border-line bg-panel/90 p-3 shadow-panel">
      <div className="text-xs uppercase tracking-[0.2em] text-muted">{props.title}</div>
      <div className={`mt-2 truncate text-lg font-semibold ${props.tone ?? "text-ink"}`}>{props.value}</div>
      {props.detail ? <div className="mt-1 truncate text-sm text-muted">{props.detail}</div> : null}
    </div>
  );
}

function KV(props: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2">
      <div className="text-xs text-muted">{props.label}</div>
      <div className="mt-0.5 truncate text-sm text-ink">{props.value}</div>
    </div>
  );
}

export function App() {
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [selectedFlowName, setSelectedFlowName] = useState<string | null>(null);
  const [dismissedJobId, setDismissedJobId] = useState<string | null>(null);
  const [activeNav, setActiveNav] = useState<NavKey>("overview");
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [issues, setIssues] = useState<IssueCaseSummary[]>([]);
  const [flows, setFlows] = useState<FlowSummary[]>([]);
  const [cards, setCards] = useState<ProtocolReplayCard[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [selectedIssueId, setSelectedIssueId] = useState<string>("");
  const [selectedReportSlug, setSelectedReportSlug] = useState<string>("progress");
  const [reportDoc, setReportDoc] = useState<MarkdownDocument | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobSummary | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedFile, setSelectedFile] = useState<FileDocument | null>(null);
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState<string>("");
  const [protoTab, setProtoTab] = useState<"parse" | "encoding" | "replay">("parse");
  const [protoMessages, setProtoMessages] = useState<ProtocolMessagesResult | null>(null);
  const [selectedProtocol, setSelectedProtocol] = useState<string>("");
  const [selectedMessageIndex, setSelectedMessageIndex] = useState<number>(-1);
  const [encodingCases, setEncodingCases] = useState<EncodingTestcase[]>([]);
  const [selectedEncodingId, setSelectedEncodingId] = useState<string>("");
  const [replayResults, setReplayResults] = useState<ReplayValidationResult | null>(null);
  const [selectedReplayIndex, setSelectedReplayIndex] = useState<number>(-1);

  const currentIssue = useMemo(
    () => selectedIssueId ? (issues.find((item) => item.id === selectedIssueId) ?? null) : (issues[0] ?? null),
    [issues, selectedIssueId]
  );

  const currentFlow = useMemo(
    () => selectedFlowName ? flows.find((item) => item.flow === selectedFlowName) ?? null : null,
    [flows, selectedFlowName]
  );

  async function loadAll() {
    try {
      const [systemData, issueData, flowData, protocolData, reportData, jobData] = await Promise.all([
        getJson<SystemStatus>("/api/status/system"),
        getJson<IssueCaseSummary[]>("/api/issues"),
        getJson<FlowSummary[]>("/api/flows/latest"),
        getJson<ProtocolReplayCard[]>("/api/protocol-replay"),
        getJson<ReportItem[]>("/api/reports"),
        getJson<JobSummary[]>("/api/jobs")
      ]);
      setSystem(systemData);
      setIssues(issueData);
      setFlows(flowData);
      setCards(protocolData);
      setReports(reportData);
      setJobs(jobData);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载失败");
    }
  }

  async function loadReport(slug: string) {
    try {
      const data = await getJson<MarkdownDocument>(`/api/reports/${slug}`);
      setReportDoc(data);
      setSelectedReportSlug(slug);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "报告加载失败");
    }
  }

  useEffect(() => {
    void loadAll();
    const timer = window.setInterval(() => {
      void loadAll();
    }, 4000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedIssueId && issues.length > 0) {
      setSelectedIssueId(issues[0].id);
    }
  }, [issues]);

  useEffect(() => {
    if (!selectedJob) {
      const runningJob = jobs.find((job) => !job.finishedAt && job.id !== dismissedJobId);
      if (runningJob) {
        setDismissedJobId(null);
        setSelectedJob(runningJob);
      }
      return;
    }
    const current = jobs.find((job) => job.id === selectedJob.id);
    if (current) {
      setSelectedJob(current);
    }
  }, [jobs]);

  useEffect(() => {
    if (activeNav === "reports" && selectedReportSlug) {
      void loadReport(selectedReportSlug);
    }
  }, [activeNav, selectedReportSlug]);

  useEffect(() => {
    if (activeNav !== "protocol-replay") return;
    if (protoMessages && encodingCases.length > 0 && replayResults) return;
    async function loadProtocolData() {
      try {
        const [msgData, encData, repData] = await Promise.all([
          getJson<ProtocolMessagesResult>("/api/protocol/messages"),
          getJson<EncodingTestcase[]>("/api/encoding/testcases"),
          getJson<ReplayValidationResult>("/api/replay/validation")
        ]);
        setProtoMessages(msgData);
        setEncodingCases(encData);
        setReplayResults(repData);
        if (msgData.protocols.length > 0 && !selectedProtocol) {
          setSelectedProtocol(msgData.protocols[0]);
        }
        if (encData.length > 0 && !selectedEncodingId) {
          setSelectedEncodingId(`${encData[0].id}_${encData[0].source}`);
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "协议数据加载失败");
      }
    }
    void loadProtocolData();
  }, [activeNav]);

  async function runRestore() {
    setBusy("restore");
    try {
      const job = await getJson<JobSummary>("/api/system/restore", { method: "POST" });
      setDismissedJobId(null);
      setSelectedJob(job);
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复失败");
    } finally {
      setBusy("");
    }
  }

  async function runIssue(caseId: string, live: boolean) {
    if (live) {
      const target = currentIssue;
      const confirmation = window.confirm(
        [
          "该 testcase 可能会故意打崩 Open5GS 网元，并在执行后自动恢复 baseline。",
          "",
          `Target: ${target?.component?.toUpperCase() ?? "UNKNOWN"}`,
          `Case: ${target?.title ?? caseId}`,
          `Expected: ${target?.latestLiveRun?.classification ?? target?.classification ?? "VULNERABLE_CRASH or SAFE_REJECT"}`,
          "",
          "确认执行 Live run 吗？"
        ].join("\n")
      );
      if (!confirmation) {
        return;
      }
    }
    setBusy(caseId);
    try {
      const job = await getJson<JobSummary>(`/api/issues/${caseId}/${live ? "live-run" : "dry-run"}`, {
        method: "POST",
        body: JSON.stringify(live ? { confirmed: true } : {})
      });
      setDismissedJobId(null);
      setSelectedJob(job);
      setActiveNav("issues");
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "执行失败");
    } finally {
      setBusy("");
    }
  }

  async function runFlow(flow: string) {
    setBusy(`flow_${flow}`);
    try {
      const job = await getJson<JobSummary>(`/api/flows/${flow}/run`, { method: "POST" });
      setDismissedJobId(null);
      setSelectedJob(job);
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Flow 执行失败");
    } finally {
      setBusy("");
    }
  }

  async function abortAndRestore() {
    if (!selectedJob) {
      return;
    }
    const confirmed = window.confirm("将终止当前任务并立即恢复 baseline。确认继续吗？");
    if (!confirmed) {
      return;
    }
    setBusy("abort");
    try {
      const job = await getJson<JobSummary>(`/api/jobs/${selectedJob.id}/abort-and-restore`, {
        method: "POST"
      });
      setDismissedJobId(null);
      setSelectedJob(job);
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "终止失败");
    } finally {
      setBusy("");
    }
  }

  async function openFile(pathValue?: string) {
    if (!pathValue) {
      return;
    }
    try {
      const file = await getJson<FileDocument>(`/api/file?path=${encodeURIComponent(pathValue)}`);
      setSelectedFile(file);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "文件读取失败");
    }
  }

  function renderOverview() {
    if (!system) {
      return null;
    }
    return (
      <div className="space-y-6">
        <SectionTitle
          title="系统总览"
          description="展示 baseline 健康、Open5GS 镜像摘要和关键容器状态。"
          action={
            <div className="flex gap-2">
              <ActionButton label="刷新状态" onClick={() => void loadAll()} disabled={busy !== ""} />
              <ActionButton label="恢复 baseline" onClick={() => void runRestore()} disabled={busy !== ""} tone="danger" />
            </div>
          }
        />
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-3">
          <SummaryCard
            title="Baseline"
            value={
              system.currentMutatingJob
                ? "执行中"
                : system.baseline.ready
                  ? "READY"
                  : "FAIL"
            }
            detail={
              system.currentMutatingJob
                ? `正在执行: ${system.currentMutatingJob.stepName}`
                : system.baseline.summary
            }
            tone={
              system.currentMutatingJob
                ? "text-warn"
                : system.baseline.ready
                  ? "text-accent"
                  : "text-danger"
            }
          />
          <SummaryCard title="Open5GS Digest" value={system.open5gsImage} detail={`Branch: ${system.branch}`} />
          <SummaryCard
            title="Last Restore"
            value={system.lastRestoreState === "ok" ? "成功" : system.lastRestoreState === "failed" ? "失败" : "未运行"}
            detail={`更新于 ${new Date(system.checkedAt).toLocaleString("zh-CN")}`}
            tone={system.lastRestoreState === "failed" ? "text-danger" : system.lastRestoreState === "ok" ? "text-accent" : "text-ink"}
          />
        </div>
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-[1.2fr_1fr]">
          <div className="rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
            <div className="mb-4 text-sm font-medium text-ink">实验拓扑</div>
            <div className="grid gap-3 text-sm text-muted md:grid-cols-3">
              {[
                ["UE / srsUE", "Registration / PDU Session"],
                ["srsran_du", "F1-C / F1-U"],
                ["srsran_cu_cp", "NGAP / E1AP / F1AP"],
                ["srsran_cu_up", "N3 / GTP-U"],
                ["amf / smf / upf", "NGAP / PFCP / SBI"],
                ["nrf", "SBI discovery"]
              ].map(([label, detail]) => (
                <div key={label} className="rounded-xl border border-line/70 bg-[#0b1524] px-3 py-3">
                  <div className="font-mono text-sm text-ink">{label}</div>
                  <div className="mt-1 text-xs text-muted">{detail}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
            <div className="mb-4 text-sm font-medium text-ink">容器状态</div>
            <div className="space-y-2">
              {system.containers.map((container) => (
                <div
                  key={container.name}
                  className="grid grid-cols-[1.3fr_0.8fr_0.6fr] items-center rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2 text-sm"
                >
                  <div className="font-mono text-ink">{container.name}</div>
                  <div className={container.running ? "text-accent" : "text-danger"}>{container.status}</div>
                  <div className="text-right text-xs text-muted">exit {container.exitCode ?? "-"}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  function renderIssues() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="Issue 测试"
          description="读取 testcase JSON 和 stage5c6 结果，支持 live-run issue 验证。"
        />
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)]">
          <div className="space-y-3">
            {issues.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedIssueId(item.id)}
                className={`w-full rounded-2xl border p-4 text-left transition ${
                  currentIssue?.id === item.id ? "border-accent bg-[#11253a]" : "border-line bg-panel/90 hover:bg-[#132136]"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 break-all font-mono text-sm text-ink">{item.title.replace(/^Open5GS\s+/i, "")}</div>
                  <span className={`text-xs font-semibold ${classForStatus(item.classification ?? "")}`}>{item.classification ?? "无结果"}</span>
                </div>
                <div className="mt-2 text-xs text-muted">{item.component.toUpperCase()} / {item.protocol}</div>
                <div className="mt-3 text-xs text-muted">{item.summary.mutation}</div>
              </button>
            ))}
          </div>
          {currentIssue ? (
            <div className="min-w-0 space-y-4 rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-ink">{currentIssue.title}</h3>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                    <span className="rounded-full border border-line px-2 py-1 font-mono">{currentIssue.component}</span>
                    <span className="rounded-full border border-line px-2 py-1 font-mono">{currentIssue.protocol}</span>
                    <span className={`rounded-full border border-line px-2 py-1 font-mono ${classForStatus(currentIssue.classification ?? "")}`}>
                      {currentIssue.classification ?? "无结果"}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <ActionButton
                    label="执行 Live run"
                    onClick={() => void runIssue(currentIssue.id, true)}
                    disabled={busy !== "" || Boolean(system?.currentMutatingJob)}
                    tone="danger"
                  />
                </div>
              </div>
              {currentIssue.description ? (
                <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3 text-sm leading-6 text-[#ced9e5]">
                  {currentIssue.description}
                </div>
              ) : null}
              {(() => {
                const job = selectedJob;
                if (!job || job.finishedAt || (job.type !== "issue_live_run" && job.type !== "issue_dry_run")) return null;
                const jobForThisIssue = (job.title ?? "").includes(currentIssue.id);
                if (!jobForThisIssue) return null;
                const isLive = job.type === "issue_live_run";
                return (
                  <div className="rounded-xl border border-warn/30 bg-warn/5 p-4 space-y-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-warn">
                      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-warn" />
                      {isLive ? "Live Run 执行中" : "Dry-Run 执行中"}
                    </div>
                    <div className="grid gap-2 text-sm">
                      <div className="flex justify-between"><span className="text-muted">阶段</span><span className="text-ink">{job.stepName}</span></div>
                      <div className="flex justify-between"><span className="text-muted">进度</span><span className="font-mono text-ink">{job.stepIndex} / {job.stepTotal}</span></div>
                      <div className="flex justify-between"><span className="text-muted">用时</span><span className="font-mono text-ink">{formatSeconds(job.elapsedSeconds)}</span></div>
                      <div className="text-xs text-muted mt-1">{job.progressLabel}</div>
                    </div>
                    {job.stdoutTail.length > 0 ? (
                      <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-line/70 bg-[#0b1524] p-3 font-mono text-xs text-[#ced9e5]">{job.stdoutTail.join("\n")}</pre>
                    ) : null}
                  </div>
                );
              })()}
              {system?.containers ? (
                <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                  <div className="mb-2 text-xs text-muted">网元状态</div>
                  <div className="grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
                    {system.containers.map((c) => {
                      const isTarget = c.name === currentIssue.component;
                      return (
                        <div key={c.name} className={`flex items-center justify-between gap-1 rounded-lg border px-2 py-1 text-xs ${isTarget ? "border-accent/50 bg-accent/5" : "border-line/50"}`}>
                          <span className={`font-mono ${isTarget ? "text-ink" : "text-muted"}`}>{c.name}</span>
                          <span className={c.running ? "text-accent" : "text-danger"}>{c.running ? "running" : c.status}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
                <KV label="Issue URL" value={<a className="text-accent" href={currentIssue.issue} target="_blank" rel="noreferrer">{currentIssue.issue}</a>} />
                <KV label="Fix / 边界" value={<span className="break-all font-mono text-xs">{currentIssue.fix}</span>} />
                <KV label="Mutation" value={<span className="font-mono text-xs">{currentIssue.summary.mutation}</span>} />
                <KV label="Request Summary" value={<span className="font-mono text-xs">{currentIssue.summary.request}</span>} />
                <KV label="Testcase JSON" value={pathTag(currentIssue.casePath)} />
                <KV label="Latest Live Result" value={pathTag(currentIssue.latestLiveRun?.path)} />
              {(() => {
                const isRunning = selectedJob && !selectedJob.finishedAt && (selectedJob.type === "issue_live_run" || selectedJob.type === "issue_dry_run") && (selectedJob.title ?? "").includes(currentIssue.id);
                if (isRunning) return null;
                let r = currentIssue.result;
                if (!r && selectedJob?.finishedAt && (selectedJob.type === "issue_live_run" || selectedJob.type === "issue_dry_run") && (selectedJob.title ?? "").includes(currentIssue.id)) {
                  r = selectedJob.resultSummary as Record<string, unknown> | undefined;
                }
                if (!r) return null;
                const classification = String(r.classification ?? "");
                const isCrash = classification === "VULNERABLE_CRASH";
                const isDryRun = classification === "DRY_RUN";
                const isSafeReject = classification === "SAFE_REJECT" || classification === "NOT_REPRODUCED";
                const before = r.target_before as { status?: string; exit_code?: number } | undefined;
                const after = r.target_after as { status?: string; exit_code?: number } | undefined;
                const req = r.request as { curl_exit_code?: number; curl_stderr?: string } | undefined;
                const restore = r.baseline_restore as { restored?: boolean } | undefined;
                const rawLogDelta = r[`${currentIssue.component}_log_delta`];
                const componentLogs = (rawLogDelta ?? r.log_delta) as Record<string, unknown> | undefined;
                const fatalHits = (componentLogs as { fatal_keyword_hits?: string[] } | undefined)?.fatal_keyword_hits;
                const pfcpErrorHits = (componentLogs as { pfcp_error_hits?: string[] } | undefined)?.pfcp_error_hits;
                const isPfcpError = classification === "PFCP_ERROR_NO_IMPACT" || classification === "ACCEPTED_OR_FIXED_BEHAVIOR";
                const pfcpRequest = r.pfcp_request as { message_type?: string; far_id?: number; payload_hex?: string } | undefined;
                const pfcpResponse = r.pfcp_response as { received?: boolean; cause?: number; cause_name?: string } | undefined;
                const pfcpSession = r.pfcp_session as { up_seid?: number; cp_seid?: number; ipv4?: string } | undefined;

                const bannerTone = isCrash ? "border-danger/50 bg-danger/10" : isPfcpError ? "border-warn/30 bg-warn/5" : isSafeReject ? "border-accent/30 bg-accent/5" : "border-warn/30 bg-warn/5";
                const bannerLabel = isCrash ? "目标网元崩溃" : isPfcpError ? "PFCP 鲁棒性验证" : isDryRun ? "Dry-Run (未实际发送)" : isSafeReject ? "安全拒绝 / 未复现" : classification;
                const bannerColor = isCrash ? "text-danger" : isSafeReject ? "text-accent" : "text-warn";

                return (
                  <div className={`rounded-xl border p-4 space-y-4 ${bannerTone}`}>
                    <div className={`text-base font-semibold ${bannerColor}`}>
                      {bannerLabel}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      <div className="rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2">
                        <div className="text-xs text-muted">目标网元 ({currentIssue.component.toUpperCase()})</div>
                        <div className="mt-1 flex items-center gap-2">
                          <span className="text-sm text-ink">{before?.status ?? "-"}</span>
                          <span className="text-muted">→</span>
                          <span className={`text-sm font-semibold ${after?.status !== before?.status ? "text-danger" : "text-ink"}`}>{after?.status ?? "-"}</span>
                        </div>
                        {typeof after?.exit_code === "number" ? <div className="mt-1 text-xs text-muted">exit code: {String(after.exit_code)}</div> : null}
                      </div>
                      <div className="rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2">
                        <div className="text-xs text-muted">请求结果</div>
                        <div className="mt-1 text-sm text-ink">{req?.curl_stderr ?? "-"}</div>
                        <div className="mt-1 text-xs text-muted">curl exit: {String(req?.curl_exit_code ?? "-")}</div>
                      </div>
                      <div className="rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2">
                        <div className="text-xs text-muted">Baseline 恢复</div>
                        <div className={`mt-1 text-sm font-semibold ${restore?.restored ? "text-accent" : "text-danger"}`}>
                          {isDryRun ? "N/A (DRY_RUN)" : restore?.restored ? "已恢复" : "恢复失败"}
                        </div>
                        {typeof r.restart_count_delta === "number" && r.restart_count_delta > 0 ? (
                          <div className="mt-1 text-xs text-danger">重启次数: +{String(r.restart_count_delta)}</div>
                        ) : null}
                      </div>
                    </div>
                    {isPfcpError && pfcpRequest ? (
                      <div className="rounded-xl border border-warn/30 bg-[#0b1524] px-3 py-2">
                        <div className="text-xs text-warn">PFCP 请求</div>
                        <div className="mt-1 space-y-1 text-xs">
                          <div className="text-[#ced9e5]">消息类型: <span className="font-mono">{pfcpRequest.message_type ?? "-"}</span></div>
                          <div className="text-[#ced9e5]">FAR-ID: <span className="font-mono">{String(pfcpRequest.far_id ?? "-")}</span></div>
                          {pfcpSession ? <div className="text-[#ced9e5]">F-SEID: <span className="font-mono">UP:0x{(pfcpSession.up_seid ?? 0).toString(16)} CP:0x{(pfcpSession.cp_seid ?? 0).toString(16)}</span></div> : null}
                        </div>
                      </div>
                    ) : null}
                    {isPfcpError && pfcpResponse ? (
                      <div className="rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2">
                        <div className="text-xs text-muted">PFCP 响应</div>
                        <div className="mt-1 space-y-1 text-xs">
                          <div className="text-[#ced9e5]">收到响应: <span className="font-mono">{pfcpResponse.received ? "是" : "否"}</span></div>
                          <div className="text-[#ced9e5]">Cause: <span className="font-mono">{pfcpResponse.cause_name ?? String(pfcpResponse.cause ?? "-")}</span></div>
                        </div>
                      </div>
                    ) : null}
                    {fatalHits && fatalHits.length > 0 ? (
                      <div className="rounded-xl border border-danger/30 bg-[#0b1524] px-3 py-2">
                        <div className="text-xs text-danger">关键日志证据 <span className="text-muted">(容器 UTC 时间)</span></div>
                        <div className="mt-1 space-y-1">
                          {fatalHits.slice(0, 3).map((hit, i) => (
                            <div key={i} className="font-mono text-xs text-[#ced9e5] break-all">{hit}</div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {pfcpErrorHits && pfcpErrorHits.length > 0 ? (
                      <div className="rounded-xl border border-warn/30 bg-[#0b1524] px-3 py-2">
                        <div className="text-xs text-warn">PFCP 错误日志 <span className="text-muted">(容器 UTC 时间)</span></div>
                        <div className="mt-1 space-y-1">
                          {pfcpErrorHits.slice(0, 5).map((hit, i) => (
                            <div key={i} className="font-mono text-xs text-[#ced9e5] break-all">{hit}</div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })()}
              <div className="flex flex-wrap gap-2">
                <ActionButton label="查看 Testcase JSON" onClick={() => void openFile(currentIssue.casePath)} />
                <ActionButton label="查看 Live 结果" onClick={() => void openFile(currentIssue.latestLiveRun?.path)} disabled={!currentIssue.latestLiveRun?.path} />
              </div>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const runningFlowJob = useMemo(() => {
    const job = selectedJob;
    if (!job || job.type !== "ue_flow") {
      return null;
    }
    if (job.status === "completed" || job.status === "completed_with_failure" || job.status === "restore_failed") {
      const summary = job.resultSummary as Record<string, unknown> | undefined;
      const liveChecks = summary?.liveChecks as Array<unknown> | undefined;
      if (liveChecks && liveChecks.length > 0 && !flows.some((f) => f.runId === String(summary?.liveRunId ?? ""))) {
        return job;
      }
      return null;
    }
    return job;
  }, [selectedJob, flows]);

  const runningFlowName = useMemo(() => {
    if (!runningFlowJob) return null;
    const title = runningFlowJob.title ?? "";
    if (title.includes("Release")) return "registration_release";
    return "registration_pdu_session";
  }, [runningFlowJob]);

  const EXPECTED_CHECKS_COMMON = [
    "NGAP:InitialUEMessage",
    "F1AP:UEContextSetupRequest",
    "F1AP:UEContextSetupResponse",
    "E1AP:BearerContextSetupRequest",
    "E1AP:BearerContextSetupResponse",
    "NGAP:PDUSessionResourceSetupRequest",
    "F1AP:UEContextModificationRequest",
    "NGAP:PDUSessionResourceSetupResponse",
    "GTP-U:current_tunnel_traffic",
    "UE:registration_accept",
    "UE:pdu_session_established",
    "CU-CP:pdu_session_state",
    "CU-UP:tunnel_state",
    "DU:ue_context_state",
    "Open5GS:session_state"
  ];
  const EXPECTED_CHECKS_RELEASE = [
    "NGAP:UEContextReleaseRequest",
    "NGAP:UEContextReleaseCommand",
    "E1AP:BearerContextReleaseCommand",
    "E1AP:BearerContextReleaseComplete",
    "F1AP:UEContextReleaseCommand",
    "F1AP:UEContextReleaseComplete",
    "NGAP:UEContextReleaseComplete",
    "CU-CP:release_state",
    "CU-UP:release_state",
    "DU:release_state",
    "Open5GS:release_state",
    "UE:rrc_release"
  ];

  function renderFlows() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="UE Flow"
          description="展示最新 Registration + PDU Session 与 Registration + Inactivity Release 结果。点击「执行测试」触发自动化流程。"
        />
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
          {flows.map((flow) => {
            const isRunning = runningFlowName === flow.flow;
            const live = isRunning ? (runningFlowJob?.resultSummary ?? {}) as Record<string, unknown> : {};
            const liveRunId = isRunning ? String(live.liveRunId ?? "") : "";
            const liveChecks = isRunning ? (live.liveChecks as Array<Record<string, unknown>> ?? []) : [];
            const liveCounts = isRunning ? (live.liveCounts as Record<string, number> ?? {}) : {};
            const liveTimeline = isRunning ? (live.liveTimeline as Array<Record<string, unknown>> ?? []) : [];

            const hasAnyLiveData = isRunning && (liveRunId || liveChecks.length > 0 || Object.keys(liveCounts).length > 0);

            const displayRunId = isRunning ? (liveRunId || null) : flow.runId;
            const displayResultPath = isRunning ? (runningFlowJob?.resultPath ?? null) : flow.resultPath;
            const displayCounts = isRunning ? liveCounts : (flow.counts ?? {});
            const displayChecks = isRunning ? liveChecks : (flow.checks ?? []);
            const displayTimeline = isRunning ? liveTimeline : (currentFlow?.timeline ?? []);
            const isSelected = selectedFlowName === flow.flow;

            function handleFlowClick() {
              if (isSelected) {
                setSelectedFlowName(null);
                setDismissedJobId(null);
                setSelectedJob(null);
                return;
              }
              setSelectedFlowName(flow.flow);
              if (!flow.runId) return;
              const matchJob = [...jobs].reverse().find((j) => {
                if (j.type !== "ue_flow") return false;
                const summary = j.resultSummary as Record<string, unknown> | undefined;
                return summary?.liveRunId === flow.runId;
              });
              if (matchJob) {
                setDismissedJobId(null);
                setSelectedJob(matchJob);
              }
            }

            return (
              <div
                key={flow.flow}
                onClick={handleFlowClick}
                className={`min-w-0 cursor-pointer rounded-2xl border bg-panel/95 p-5 shadow-panel transition ${isSelected ? "border-accent" : "border-line hover:border-accent/50"}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-lg font-semibold text-ink">{flow.label}</h3>
                  <div className="flex items-center gap-3">
                    {isRunning ? (
                      <span className="flex items-center gap-1.5 font-mono text-sm text-warn">
                        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-warn" />
                        RUNNING
                      </span>
                    ) : (
                      <span className={`font-mono text-sm ${classForStatus(flow.result ?? flow.status)}`}>{flow.result ?? flow.status.toUpperCase()}</span>
                    )}
                  </div>
                </div>

                <div className="mt-4 grid gap-3">
                  <KV
                    label="Run ID"
                    value={
                      displayRunId
                        ? <span className="font-mono text-xs">{displayRunId}</span>
                        : <span className="text-muted">等待中...</span>
                    }
                  />
                  <KV label="Result JSON" value={displayResultPath ? pathTag(displayResultPath) : <span className="text-muted">-</span>} />
                  <KV
                    label="Timeline Events (含 GTP-U)"
                    value={
                      (displayCounts as Record<string, number>).timeline_events != null
                        ? <span className="font-mono">{String((displayCounts as Record<string, number>).timeline_events)}</span>
                        : <span className="text-muted">-</span>
                    }
                  />
                  <KV
                    label="Control Messages (F1AP/E1AP/NGAP)"
                    value={
                      (displayCounts as Record<string, number>).control_messages != null
                        ? <span className="font-mono">{String((displayCounts as Record<string, number>).control_messages)}</span>
                        : <span className="text-muted">-</span>
                    }
                  />
                  <KV label="Logs" value={pathTag(flow.artifacts?.logs)} />
                </div>

                {isRunning && !hasAnyLiveData ? (
                  <div className="mt-3 rounded-xl border border-warn/30 bg-warn/5 px-3 py-2 text-xs text-warn">
                    {runningFlowJob?.stepName} — {runningFlowJob?.progressLabel}
                  </div>
                ) : null}

                <div className="mt-4 flex flex-wrap gap-2">
                  <ActionButton
                    label={isRunning ? "执行中..." : "执行测试"}
                    onClick={() => void runFlow(flow.flow)}
                    disabled={busy !== "" || Boolean(system?.currentMutatingJob)}
                    tone="danger"
                  />
                  <ActionButton label="查看结果 JSON" onClick={() => void openFile(displayResultPath ?? undefined)} disabled={!displayResultPath} />
                  <ActionButton label="查看 logs 路径" onClick={() => void openFile(flow.artifacts?.logs)} disabled={!flow.artifacts?.logs} />
                </div>

                <div className="mt-4 rounded-xl border border-line/70 bg-[#0b1524] p-3">
                  <div className="mb-2 text-xs text-muted">关键检查</div>
                  {(() => {
                    const expectedNames = [
                      ...EXPECTED_CHECKS_COMMON,
                      ...(flow.flow === "registration_release" ? EXPECTED_CHECKS_RELEASE : [])
                    ];
                    const liveCheckMap = new Map<string, boolean>();
                    for (const c of displayChecks as Array<Record<string, unknown>>) {
                      liveCheckMap.set(String(c.name), Boolean(c.passed));
                    }
                    const hasAny = isRunning
                      ? liveCheckMap.size > 0
                      : displayChecks.length > 0;
                    if (!hasAny) {
                      return <div className="text-sm text-muted">{isRunning ? "等待测试完成..." : "暂无检查结果。"}</div>;
                    }
                    const rows = isRunning
                      ? expectedNames.map((name) => ({ name, status: liveCheckMap.has(name) ? (liveCheckMap.get(name) ? "PASS" : "MISS") : "pending" as const }))
                      : (displayChecks as Array<Record<string, unknown>>).map((c) => ({ name: String(c.name), status: Boolean(c.passed) ? "PASS" as const : "MISS" as const }));
                    return (
                      <div className="grid gap-2">
                        {rows.map((row) => (
                          <div key={row.name} className="flex items-start justify-between gap-3 text-sm">
                            <div className="text-ink">{row.name}</div>
                            {row.status === "pending" ? (
                              <span className="text-muted">...</span>
                            ) : row.status === "PASS" ? (
                              <span className="text-accent">PASS</span>
                            ) : (
                              <span className="text-danger">MISS</span>
                            )}
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                </div>
              </div>
            );
          })}
        </div>
        {(() => {
          const activeFlowName = selectedFlowName ?? runningFlowName;
          if (!activeFlowName) return null;
          const tlFlow = flows.find((f) => f.flow === activeFlowName);
          const tlLive = runningFlowJob?.resultSummary as Record<string, unknown> | undefined;
          const tlItems = activeFlowName === runningFlowName && runningFlowJob
            ? (tlLive?.liveTimeline as Array<Record<string, unknown>> ?? [])
            : (tlFlow?.timeline ?? []);
          const isReleaseFlow = activeFlowName === "registration_release";
          const displayedItems = isReleaseFlow ? tlItems.slice(-20) : tlItems.slice(0, 15);
          return displayedItems.length > 0 ? (
          <div className="rounded-2xl border border-accent/40 bg-panel/95 p-5 shadow-panel">
            <div className="mb-4 text-lg font-semibold text-ink">
              时间线预览 — {tlFlow?.label ?? activeFlowName}
              {isReleaseFlow && tlItems.length > 20 ? <span className="ml-2 text-sm font-normal text-muted">(显示最后 20 条)</span> : null}
            </div>
            <div className="space-y-2">
              {displayedItems.map((event, index) => (
                <div key={`${String(event.protocol)}_${index}`} className="grid grid-cols-[0.8fr_1fr_1.2fr] gap-3 rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2 text-sm">
                  <div className="font-mono text-muted">{String(event.protocol)}</div>
                  <div className="text-ink">{String(event.message)}</div>
                  <div className="text-muted">{String(event.direction)}</div>
                </div>
              ))}
            </div>
          </div>
          ) : null;
        })()}
      </div>
    );
  }

  const filteredProtoMessages = useMemo(() => {
    if (!protoMessages) return [];
    return protoMessages.messages.filter((m) => m.protocol === selectedProtocol);
  }, [protoMessages, selectedProtocol]);

  const currentEncoding = useMemo(
    () => encodingCases.find((c) => `${c.id}_${c.source}` === selectedEncodingId) ?? null,
    [encodingCases, selectedEncodingId]
  );

  const encodingByProtocol = useMemo(() => {
    const groups = new Map<string, EncodingTestcase[]>();
    for (const tc of encodingCases) {
      const list = groups.get(tc.protocol) ?? [];
      list.push(tc);
      groups.set(tc.protocol, list);
    }
    return groups;
  }, [encodingCases]);

  function renderProtocolReplay() {
    const filteredMessages = filteredProtoMessages;

    const selectedMessage = selectedMessageIndex >= 0 ? filteredMessages[selectedMessageIndex] ?? null : null;

    const selectedReplayCase = selectedReplayIndex >= 0 ? replayResults?.controlCases[selectedReplayIndex] ?? null : null;

    const tabClass = (tab: "parse" | "encoding" | "replay") =>
      `px-4 py-2 text-sm font-medium transition rounded-t-lg border-b-2 ${
        protoTab === tab
          ? "border-accent text-accent bg-[#11253a]"
          : "border-transparent text-muted hover:text-ink hover:bg-[#0b1524]"
      }`;

    return (
      <div className="space-y-4">
        <SectionTitle
          title="协议 / 回放"
          description="交互式浏览解析结果、编码 testcase 和回放验证证据。"
        />
        <div className="flex gap-1 border-b border-line">
          <button type="button" onClick={() => setProtoTab("parse")} className={tabClass("parse")}>解析浏览器</button>
          <button type="button" onClick={() => setProtoTab("encoding")} className={tabClass("encoding")}>编码 Testcase</button>
          <button type="button" onClick={() => setProtoTab("replay")} className={tabClass("replay")}>回放验证</button>
        </div>

        {protoTab === "parse" ? (
          <div className="grid gap-4 grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)]">
            <div className="scrollbar-thin max-h-[70vh] space-y-2 overflow-y-auto">
              {protoMessages ? (
                protoMessages.protocols.map((proto) => {
                  const count = protoMessages.messages.filter((m) => m.protocol === proto).length;
                  const isExpanded = selectedProtocol === proto;
                  const protoMsgs = isExpanded ? filteredMessages : [];
                  return (
                    <div key={proto}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedProtocol(proto);
                          setSelectedMessageIndex(-1);
                        }}
                        className={`w-full rounded-xl border p-3 text-left transition ${
                          isExpanded ? "border-accent bg-[#11253a]" : "border-line bg-panel/90 hover:bg-[#132136]"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-sm font-semibold text-ink">{proto}</span>
                          <span className="text-xs text-muted">{count}</span>
                        </div>
                      </button>
                      {isExpanded ? (
                        <div className="mt-1 space-y-1 pl-2">
                          {protoMsgs.map((msg, idx) => {
                            const name = msg.procedure.name || msg.info.split(",")[0].replace(/SACK\s*\(.*?\)\s*,?\s*/g, "").trim();
                            return (
                              <button
                                key={`${msg.frame}_${idx}`}
                                type="button"
                                onClick={() => setSelectedMessageIndex(idx)}
                                className={`w-full rounded-lg border px-2.5 py-1.5 text-left text-xs transition ${
                                  selectedMessageIndex === idx
                                    ? "border-accent/50 bg-accent/10 text-ink"
                                    : "border-line/50 bg-[#0b1524] text-muted hover:text-ink"
                                }`}
                              >
                                <span className="font-mono">{msg.frame}</span>
                                <span className="mx-1 text-muted/50">|</span>
                                <span className="truncate">{name}</span>
                              </button>
                            );
                          })}
                        </div>
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <div className="text-sm text-muted">加载中...</div>
              )}
            </div>

            <div className="min-w-0 rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
              {selectedMessage ? (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold text-ink">
                      {selectedMessage.procedure.name || selectedMessage.info.split(",")[0].replace(/SACK\s*\(.*?\)\s*,?\s*/g, "").trim()}
                    </h3>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                      <span className="rounded-full border border-line px-2 py-1 font-mono">{selectedMessage.protocol}</span>
                      <span className="rounded-full border border-line px-2 py-1 font-mono">
                        Procedure Code: {selectedMessage.procedure.code}
                      </span>
                      <span className="rounded-full border border-line px-2 py-1 font-mono">
                        Frame #{selectedMessage.frame}
                      </span>
                    </div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <KV
                      label="方向"
                      value={
                        <span className="font-mono text-xs">
                          {selectedMessage.ip.src}{selectedMessage.sctp ? `:${selectedMessage.sctp.srcport}` : ""} → {selectedMessage.ip.dst}{selectedMessage.sctp ? `:${selectedMessage.sctp.dstport}` : ""}
                        </span>
                      }
                    />
                    <KV label="来源" value={<span className="text-xs">{protoMessages?.sources.find((s) => s.id === selectedMessage.source)?.label ?? selectedMessage.source}</span>} />
                  </div>
                  {selectedMessage.protocol === "GTP-U" && selectedMessage.gtp ? (
                    <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                      <div className="mb-2 text-xs text-muted">GTP-U / NRUP 信息</div>
                      <div className="grid gap-2 text-xs">
                        {Object.entries(selectedMessage.gtp).map(([k, v]) => (
                          <div key={k} className="flex gap-2">
                            <span className="text-muted">{k}:</span>
                            <span className="font-mono text-[#ced9e5]">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {Object.keys(selectedMessage.ies).length > 0 ? (
                    <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                      <div className="mb-2 text-xs text-muted">关键 IE</div>
                      <div className="space-y-2">
                        {Object.entries(selectedMessage.ies).map(([k, v]) => (
                          <div key={k} className="flex items-start justify-between gap-3 text-sm">
                            <span className="text-muted">{k}</span>
                            <span className="font-mono text-xs text-[#ced9e5] break-all text-right">
                              {typeof v === "object" ? JSON.stringify(v) : String(v)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3 text-sm text-muted">
                      此消息无结构化 IE 数据。
                    </div>
                  )}
                  <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                    <div className="mb-2 text-xs text-muted">完整 Info</div>
                    <div className="text-sm text-[#ced9e5] break-all">{selectedMessage.info}</div>
                  </div>
                  <div className="flex gap-2">
                    <ActionButton
                      label="查看原始 JSON"
                      onClick={() => {
                        setSelectedFile({ path: `protocol://${selectedMessage.protocol}/${selectedMessage.frame}`, content: JSON.stringify(selectedMessage, null, 2) });
                      }}
                    />
                  </div>
                </div>
              ) : (
                <div className="text-sm text-muted">选择左侧协议和消息查看详情。</div>
              )}
            </div>
          </div>
        ) : null}

        {protoTab === "encoding" ? (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-3 rounded-xl border border-line/70 bg-[#0b1524] px-4 py-2.5 text-xs text-muted">
              <span><span className="font-semibold text-ink">case</span> — 从真实抓包提取报文，替换部分字段（如 UE ID）后重新编码成 pcap，由 Wireshark 离线验证合法性，证明编码可逆</span>
              <span className="text-line">|</span>
              <span><span className="font-semibold text-ink">template</span> — 从真实抓包直接提取的原始报文，未做任何修改</span>
              <span className="text-line">|</span>
              <span><span className="font-semibold text-ink">live</span> — 用 JSON 参数动态构造报文，在线发送到运行中的 RAN 网元（CU-CP / DU / CU-UP），验证真实组件能否正确处理</span>
            </div>
            <div className="grid gap-4 grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)]">
            <div className="scrollbar-thin max-h-[70vh] space-y-3 overflow-y-auto">
              {[...encodingByProtocol.entries()].map(([proto, cases]) => (
                <div key={proto}>
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">{proto} ({cases.length})</div>
                  <div className="space-y-1">
                    {cases.map((tc) => (
                      <button
                        key={tc.id}
                        type="button"
                        onClick={() => setSelectedEncodingId(`${tc.id}_${tc.source}`)}
                        className={`w-full rounded-xl border p-3 text-left transition ${
                          selectedEncodingId === `${tc.id}_${tc.source}` ? "border-accent bg-[#11253a]" : "border-line bg-panel/90 hover:bg-[#132136]"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm text-ink">{tc.id}</span>
                          <span className="shrink-0 rounded-full border border-line px-1.5 py-0.5 text-[10px] text-muted">
                            {tc.source === "cases" ? "case" : tc.source === "live_cases" ? "live" : "template"}
                          </span>
                        </div>
                        {tc.message ? <div className="mt-1 text-xs text-muted">{tc.message}</div> : null}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {encodingCases.length === 0 ? <div className="text-sm text-muted">加载中...</div> : null}
            </div>

            <div className="min-w-0 rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
              {currentEncoding ? (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold text-ink">{currentEncoding.id}</h3>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                      <span className="rounded-full border border-line px-2 py-1 font-mono">{currentEncoding.protocol}</span>
                      {currentEncoding.message ? (
                        <span className="rounded-full border border-line px-2 py-1 font-mono">{currentEncoding.message}</span>
                      ) : null}
                      <span className="rounded-full border border-line px-2 py-1">
                        {currentEncoding.source === "cases" ? "Replay Case" : currentEncoding.source === "live_cases" ? "Live Peer" : "Template"}
                      </span>
                    </div>
                  </div>
                  {currentEncoding.description ? (
                    <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3 text-sm leading-6 text-[#ced9e5]">
                      {currentEncoding.description}
                    </div>
                  ) : null}
                  {currentEncoding.structuredIes && Object.keys(currentEncoding.structuredIes).length > 0 ? (
                    <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                      <div className="mb-2 text-xs text-muted">结构化 IE</div>
                      <div className="space-y-2">
                        {Object.entries(currentEncoding.structuredIes).map(([k, v]) => (
                          <div key={k} className="flex items-start justify-between gap-3 text-sm">
                            <span className="text-muted">{k}</span>
                            <span className="font-mono text-xs text-[#ced9e5] break-all text-right">
                              {typeof v === "object" ? JSON.stringify(v) : String(v)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {currentEncoding.mutation && Object.keys(currentEncoding.mutation).length > 0 ? (
                    <div className="rounded-xl border border-warn/30 bg-warn/5 px-4 py-3">
                      <div className="mb-2 text-xs text-warn">Mutation</div>
                      <div className="space-y-2">
                        {Object.entries(currentEncoding.mutation).map(([k, v]) => (
                          <div key={k} className="flex items-start justify-between gap-3 text-sm">
                            <span className="text-muted">{k}</span>
                            <span className="font-mono text-xs text-[#ced9e5] break-all text-right">
                              {typeof v === "object" ? JSON.stringify(v) : String(v)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {currentEncoding.expect ? (
                    <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                      <div className="mb-2 text-xs text-muted">验证预期</div>
                      {(() => {
                        const exp = currentEncoding.expect as Record<string, unknown>;
                        const df = exp.display_filter as string | undefined;
                        const fields = exp.fields as Record<string, string> | undefined;
                        return (
                          <div className="space-y-2">
                            {df ? (
                              <div className="flex items-start justify-between gap-3 text-sm">
                                <span className="text-muted">display_filter</span>
                                <span className="font-mono text-xs text-[#ced9e5] break-all text-right">{df}</span>
                              </div>
                            ) : null}
                            {fields ? Object.entries(fields).map(([k, v]) => (
                              <div key={k} className="flex items-start justify-between gap-3 text-sm">
                                <span className="text-muted">{k}</span>
                                <span className="font-mono text-xs text-[#ced9e5] break-all text-right">{String(v)}</span>
                              </div>
                            )) : null}
                          </div>
                        );
                      })()}
                    </div>
                  ) : null}
                  <div className="flex gap-2">
                    <ActionButton label="查看完整 JSON" onClick={() => void openFile(currentEncoding.path)} />
                  </div>
                </div>
              ) : (
                <div className="text-sm text-muted">选择左侧 testcase 查看详情。</div>
              )}
            </div>
          </div>
          </div>
        ) : null}

        {protoTab === "replay" ? (
          <div className="grid gap-4 grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)]">
            <div className="scrollbar-thin max-h-[70vh] space-y-2 overflow-y-auto">
              {replayResults ? (
                replayResults.controlCases.map((c, idx) => {
                  const levelKeys = Object.keys(c.levels).sort();
                  const allPass = levelKeys.length > 0 && levelKeys.every((k) => c.levels[k]);
                  const anyFail = levelKeys.some((k) => !c.levels[k]);
                  return (
                    <button
                      key={`${c.source}_${idx}`}
                      type="button"
                      onClick={() => setSelectedReplayIndex(idx)}
                      className={`w-full rounded-xl border p-3 text-left transition ${
                        selectedReplayIndex === idx ? "border-accent bg-[#11253a]" : "border-line bg-panel/90 hover:bg-[#132136]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm text-ink">{c.protocol} / {c.message}</span>
                        <span className={`shrink-0 text-xs font-semibold ${allPass ? "text-accent" : anyFail ? "text-danger" : "text-muted"}`}>
                          {allPass ? "ALL PASS" : anyFail ? "PARTIAL" : "-"}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-muted">Peer: {c.peer}</div>
                      <div className="mt-1 flex gap-1">
                        {levelKeys.map((lk) => (
                          <span
                            key={lk}
                            className={`rounded px-1 py-0.5 text-[10px] font-mono ${
                              c.levels[lk] ? "bg-accent/20 text-accent" : "bg-danger/20 text-danger"
                            }`}
                          >
                            {lk}
                          </span>
                        ))}
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="text-sm text-muted">加载中...</div>
              )}
            </div>

            <div className="min-w-0 rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
              {selectedReplayCase ? (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold text-ink">{selectedReplayCase.protocol} / {selectedReplayCase.message}</h3>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                      <span className="rounded-full border border-line px-2 py-1 font-mono">{selectedReplayCase.protocol}</span>
                      <span className="rounded-full border border-line px-2 py-1 font-mono">Peer: {selectedReplayCase.peer}</span>
                      <span className="rounded-full border border-line px-2 py-1">{selectedReplayCase.source}</span>
                    </div>
                  </div>

                  <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                    <div className="mb-2 text-xs text-muted">验证级别</div>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      {Object.entries(selectedReplayCase.levels).sort(([a], [b]) => a.localeCompare(b)).map(([level, passed]) => (
                        <div key={level} className={`rounded-lg border px-3 py-2 ${passed ? "border-accent/30 bg-accent/5" : "border-danger/30 bg-danger/5"}`}>
                          <div className="text-xs text-muted">{level}</div>
                          <div className={`mt-1 text-sm font-semibold ${passed ? "text-accent" : "text-danger"}`}>
                            {passed ? "PASS" : "FAIL"}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {selectedReplayCase.payloadHashes ? (() => {
                    const hashes = selectedReplayCase.payloadHashes as Record<string, unknown>;
                    const allEqual = hashes.all_equal as boolean | undefined;
                    return (
                      <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                        <div className="mb-2 text-xs text-muted">Payload Hash 一致性</div>
                        <div className={`text-sm font-semibold ${allEqual ? "text-accent" : "text-danger"}`}>
                          {allEqual ? "全部一致" : "不一致"}
                        </div>
                        <div className="mt-2 space-y-1">
                          {Object.entries(hashes).filter(([k]) => k.endsWith("_sha256")).map(([k, v]) => (
                            <div key={k} className="text-xs">
                              <span className="text-muted">{k.replace(/_sha256$/, "")}:</span>
                              <span className="ml-2 font-mono text-[#ced9e5] break-all">{String(v).slice(0, 16)}...</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })() : null}

                  {selectedReplayCase.l2Tshark ? (() => {
                    const tshark = selectedReplayCase.l2Tshark as Record<string, unknown>;
                    const fieldChecks = tshark.field_checks as Record<string, { expected?: string; actual?: string; passed?: boolean }> | undefined;
                    const recognized = tshark.protocol_recognized as boolean | undefined;
                    const pcapMatch = tshark.pcap_payload_matches_generated as boolean | undefined;
                    return (
                      <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                        <div className="mb-2 text-xs text-muted">tshark / Wireshark 验证</div>
                        <div className="grid gap-2 sm:grid-cols-3">
                          <div className="rounded-lg border border-line/50 px-2 py-1.5">
                            <div className="text-[10px] text-muted">协议识别</div>
                            <div className={`text-sm font-semibold ${recognized ? "text-accent" : "text-danger"}`}>{recognized ? "PASS" : "FAIL"}</div>
                          </div>
                          <div className="rounded-lg border border-line/50 px-2 py-1.5">
                            <div className="text-[10px] text-muted">Pcap Hash 匹配</div>
                            <div className={`text-sm font-semibold ${pcapMatch ? "text-accent" : "text-danger"}`}>{pcapMatch ? "PASS" : "FAIL"}</div>
                          </div>
                          <div className="rounded-lg border border-line/50 px-2 py-1.5">
                            <div className="text-[10px] text-muted">总体</div>
                            <div className={`text-sm font-semibold ${(tshark.passed as boolean | undefined) ? "text-accent" : "text-danger"}`}>
                              {(tshark.passed as boolean | undefined) ? "PASS" : "FAIL"}
                            </div>
                          </div>
                        </div>
                        {fieldChecks ? (
                          <div className="mt-3 space-y-1">
                            <div className="text-[10px] text-muted">字段检查</div>
                            {Object.entries(fieldChecks).map(([field, check]) => (
                              <div key={field} className="flex items-center justify-between gap-2 text-xs">
                                <span className="text-[#ced9e5] font-mono">{field}</span>
                                <span className={check.passed ? "text-accent" : "text-danger"}>
                                  {String(check.actual)} {check.passed ? "=" : "≠"} {String(check.expected)}
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  })() : null}

                  {selectedReplayCase.evidence ? (
                    <div className="rounded-xl border border-line/70 bg-[#0b1524] px-4 py-3">
                      <div className="mb-2 text-xs text-muted">对端交互证据</div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {Object.entries(selectedReplayCase.evidence).map(([k, v]) => (
                          <div key={k} className="flex items-center justify-between gap-2 rounded-lg border border-line/50 px-2 py-1.5">
                            <span className="text-xs text-[#ced9e5]">{k}</span>
                            <span className={`text-xs font-semibold ${v ? "text-accent" : "text-danger"}`}>{v ? "YES" : "NO"}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {(() => {
                    const caseIdx = selectedReplayIndex;
                    if (!replayResults) return null;
                    const rc = replayResults.controlCases[caseIdx];
                    if (rc?.source === "ngap_open5gs" && replayResults.ngapCase) {
                      const ngap = replayResults.ngapCase;
                      const mutation = ngap.mutation as Record<string, unknown> | undefined;
                      const observations = ngap.observations as Record<string, unknown> | undefined;
                      const checks = ngap.checks as Record<string, boolean> | undefined;
                      return (
                        <div className="rounded-xl border border-accent/30 bg-accent/5 px-4 py-3">
                          <div className="mb-2 text-xs text-accent">NGAP Configuration Mutation</div>
                          {mutation ? (
                            <div className="mb-2 text-xs text-[#ced9e5]">
                              Mutation: <span className="font-mono">{String(mutation.field)} = {String(mutation.value)}</span>
                            </div>
                          ) : null}
                          {observations ? (
                            <div className="space-y-1 text-xs text-[#ced9e5]">
                              {Object.entries(observations).map(([k, v]) => (
                                <div key={k}>{k}: <span className="font-mono">{String(v)}</span></div>
                              ))}
                            </div>
                          ) : null}
                          {checks ? (
                            <div className="mt-2 space-y-1">
                              {Object.entries(checks).map(([k, v]) => (
                                <div key={k} className="flex items-center justify-between gap-2 text-xs">
                                  <span className="text-[#ced9e5]">{k}</span>
                                  <span className={v ? "text-accent" : "text-danger"}>{v ? "PASS" : "FAIL"}</span>
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      );
                    }
                    if (rc?.source === "peer_validation" && rc.protocol === "GTP-U" && replayResults.gtpu) {
                      const gtpu = replayResults.gtpu;
                      const gtpuLevels = gtpu.levels as Record<string, boolean> | undefined;
                      const gtpuChecks = gtpu.checks as Record<string, boolean> | undefined;
                      const session = gtpu.session as Record<string, unknown> | undefined;
                      return (
                        <div className="rounded-xl border border-accent/30 bg-accent/5 px-4 py-3">
                          <div className="mb-2 text-xs text-accent">GTP-U Live Replay</div>
                          {session ? (
                            <div className="mb-2 space-y-1 text-xs text-[#ced9e5]">
                              {Object.entries(session).map(([k, v]) => (
                                <div key={k}>{k}: <span className="font-mono">{String(v)}</span></div>
                              ))}
                            </div>
                          ) : null}
                          {gtpuChecks ? (
                            <div className="space-y-1">
                              {Object.entries(gtpuChecks).map(([k, v]) => (
                                <div key={k} className="flex items-center justify-between gap-2 text-xs">
                                  <span className="text-[#ced9e5]">{k}</span>
                                  <span className={v ? "text-accent" : "text-danger"}>{v ? "PASS" : "FAIL"}</span>
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      );
                    }
                    return null;
                  })()}
                </div>
              ) : (
                <div className="text-sm text-muted">选择左侧验证 case 查看详情。</div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  function renderReports() {
    return (
      <div className="space-y-6">
        <SectionTitle title="报告" description="渲染 docs/progress.md、IMPLEMENTATION.md 和阶段 testcase 报告。" />
        <div className="grid gap-4 xl:grid-cols-[280px_1fr]">
          <div className="space-y-3">
            {reports.map((item) => (
              <button
                key={item.slug}
                type="button"
                onClick={() => void loadReport(item.slug)}
                className={`w-full rounded-2xl border p-4 text-left transition ${
                  selectedReportSlug === item.slug ? "border-accent bg-[#11253a]" : "border-line bg-panel/90 hover:bg-[#132136]"
                }`}
              >
                <div className="text-sm font-semibold text-ink">{item.title}</div>
                <div className="mt-2 font-mono text-xs text-muted">{item.path}</div>
              </button>
            ))}
            {currentIssue ? (
              <div className="rounded-2xl border border-line bg-panel/90 p-4">
                <div className="text-sm font-semibold text-ink">关键 JSON 文件</div>
                <div className="mt-3 space-y-2 text-xs text-muted">
                  <button type="button" className="block text-left hover:text-accent" onClick={() => void openFile(currentIssue.casePath)}>
                    {currentIssue.casePath}
                  </button>
                  {currentIssue.resultPath ? (
                    <button type="button" className="block text-left hover:text-accent" onClick={() => void openFile(currentIssue.resultPath)}>
                      {currentIssue.resultPath}
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
          <div className="rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
            {reportDoc ? (
              <>
                <div className="mb-4 border-b border-line pb-4">
                  <div className="text-lg font-semibold text-ink">{reportDoc.title}</div>
                  <div className="mt-2 font-mono text-xs text-muted">{reportDoc.path}</div>
                </div>
                <div className="scrollbar-thin max-h-[70vh] overflow-auto pr-2">
                  <article className="prose prose-invert max-w-none break-words prose-pre:overflow-x-auto prose-pre:bg-[#0b1524] prose-code:whitespace-pre-wrap prose-code:break-all prose-code:font-mono prose-headings:text-ink prose-p:text-[#ced9e5] prose-li:text-[#ced9e5]">
                    <ReactMarkdown>{reportDoc.content}</ReactMarkdown>
                  </article>
                </div>
              </>
            ) : (
              <div className="text-sm text-muted">请选择左侧报告。</div>
            )}
          </div>
        </div>
      </div>
    );
  }

  const panelIdle =
    selectedJob && selectedJob.status === "running" && (selectedJob.idleSeconds ?? 0) >= 20
      ? "暂无新日志，仍在等待当前阶段完成。"
      : "";

  return (
    <div className="min-h-screen bg-shell text-ink">
      <div className={`mx-auto grid min-h-screen grid-cols-1 gap-3 p-3 lg:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_360px] ${rightCollapsed ? "xl:!grid-cols-[220px_minmax(0,1fr)_48px]" : ""}`}>
        <aside className="hidden rounded-2xl border border-line bg-panel/90 p-3 lg:block">
          <div className="rounded-xl border border-line/70 bg-[#0b1524] p-3">
            <div className="text-xs uppercase tracking-[0.3em] text-muted">5G O-RAN</div>
            <div className="mt-1 text-lg font-semibold">测试控制台</div>
          </div>
          <nav className="mt-3 space-y-1">
            {navItems.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setActiveNav(item.key)}
                className={`w-full rounded-xl border p-3 text-left transition ${
                  activeNav === item.key ? "border-accent bg-[#11253a]" : "border-line bg-[#0b1524] hover:bg-[#122137]"
                }`}
              >
                <div className="text-sm font-semibold text-ink">{item.label}</div>
                <div className="mt-0.5 text-xs text-muted">{item.description}</div>
              </button>
            ))}
          </nav>
        </aside>

        <nav className="flex gap-2 overflow-x-auto lg:hidden">
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setActiveNav(item.key)}
              className={`shrink-0 rounded-xl border px-3 py-2 text-left text-sm transition ${
                activeNav === item.key ? "border-accent bg-[#11253a] text-ink" : "border-line bg-panel/90 text-muted hover:bg-[#122137]"
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <main className="min-w-0 space-y-3">
          <div className="rounded-2xl border border-line bg-panel/90 p-3 shadow-panel">
            <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
              <SummaryCard
                title="Baseline 状态"
                value={
                  system?.currentMutatingJob
                    ? "执行中"
                    : system?.baseline.ready
                      ? "READY"
                      : "FAIL"
                }
                detail={
                  system?.currentMutatingJob
                    ? `正在执行: ${system.currentMutatingJob.stepName}`
                    : system?.baseline.summary ?? "加载中"
                }
                tone={
                  system?.currentMutatingJob
                    ? "text-warn"
                    : system?.baseline.ready
                      ? "text-accent"
                      : "text-danger"
                }
              />
              <SummaryCard title="当前 Branch / Open5GS" value={system?.branch ?? "loading"} detail={system?.open5gsImage ?? "loading"} />
              <SummaryCard
                title="当前任务"
                value={system?.currentMutatingJob?.stepName ?? "空闲"}
                detail={system?.currentMutatingJob ? `${formatJobStatus(system.currentMutatingJob.status)} / ${formatSeconds(system.currentMutatingJob.elapsedSeconds)}` : "当前没有 mutating job"}
                tone={system?.currentMutatingJob ? "text-warn" : "text-accent"}
              />
            </div>
            {error ? <div className="mt-3 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</div> : null}
          </div>

          <div className="min-w-0 rounded-2xl border border-line bg-panel/90 p-4 shadow-panel">
            {activeNav === "overview" ? renderOverview() : null}
            {activeNav === "issues" ? renderIssues() : null}
            {activeNav === "ue-flow" ? renderFlows() : null}
            {activeNav === "protocol-replay" ? renderProtocolReplay() : null}
            {/* {activeNav === "reports" ? renderReports() : null } */}
          </div>
        </main>

        <aside className="hidden min-w-0 rounded-2xl border border-line bg-panel/90 p-3 shadow-panel xl:block">
          {rightCollapsed ? (
            <div className="flex flex-col items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setRightCollapsed(false)}
                className="rounded-xl border border-line bg-[#0b1524] px-2 py-2 text-xs text-muted transition hover:bg-[#122137] hover:text-ink"
                title="展开面板"
              >
                ◀
              </button>
            </div>
          ) : (
          <>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-ink">日志与结果</div>
              <div className="mt-1 text-xs text-muted">右侧固定显示最近任务和当前选中文件。</div>
            </div>
            <div className="flex items-center gap-2">
              {selectedJob?.abortable ? (
                <ActionButton
                  label="中止并恢复"
                  tone="danger"
                  onClick={() => void abortAndRestore()}
                  disabled={busy === "abort"}
                />
              ) : null}
              <button
                type="button"
                onClick={() => setRightCollapsed(true)}
                className="rounded-xl border border-line bg-[#0b1524] px-2 py-1 text-xs text-muted transition hover:bg-[#122137] hover:text-ink"
                title="收起面板"
              >
                ▶
              </button>
            </div>
          </div>
          <div className="scrollbar-thin space-y-3 overflow-y-auto pr-1 xl:max-h-[calc(100vh-100px)]">
            {selectedJob ? (
            <div className="rounded-2xl border border-line bg-[#0b1524] p-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-ink">当前任务</div>
                <button
                  type="button"
                  onClick={() => { if (selectedJob) { setDismissedJobId(selectedJob.id); setSelectedJob(null); } }}
                  className="rounded-lg border border-line px-1.5 py-0.5 text-xs text-muted transition hover:bg-[#122137] hover:text-ink"
                  title="关闭"
                >
                  ✕
                </button>
              </div>
                <div className="mt-3 space-y-3 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <div className="break-all font-mono text-xs text-muted">{selectedJob.id}</div>
                    <div className={`font-mono text-xs ${classForStatus(selectedJob.status)}`}>{formatJobStatus(selectedJob.status)}</div>
                  </div>
                  <div className="rounded-xl border border-line/70 bg-panel px-3 py-2">
                    <div className="text-xs text-muted">阶段</div>
                    <div className="mt-1 break-all text-ink">{`Step ${selectedJob.stepIndex} / ${selectedJob.stepTotal}: ${selectedJob.stepName}`}</div>
                    <div className="mt-1 break-all text-xs text-muted">{selectedJob.progressLabel}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <KV label="运行时间" value={<span className="font-mono">{formatSeconds(selectedJob.elapsedSeconds)}</span>} />
                    <KV label="阶段用时" value={<span className="font-mono">{formatSeconds(selectedJob.stageElapsedSeconds)}</span>} />
                  </div>
                  {panelIdle ? <div className="rounded-xl border border-line/70 bg-panel px-3 py-2 text-xs text-muted">{panelIdle}</div> : null}
                  {selectedJob.resultPath ? <KV label="Result JSON" value={pathTag(selectedJob.resultPath)} /> : null}
                  {selectedJob.resultSummary ? (
                    <KV
                      label="结果摘要"
                      value={<pre className="whitespace-pre-wrap break-all font-mono text-xs text-[#ced9e5]">{summarizeResultSummary(selectedJob.resultSummary)}</pre>}
                    />
                  ) : null}
                  <div>
                    <div className="mb-2 text-xs text-muted">stdout tail</div>
                    <pre className="scrollbar-thin max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-xl border border-line/70 bg-panel p-3 font-mono text-xs text-[#ced9e5]">
                      {selectedJob.stdoutTail.join("\n") || "无 stdout"}
                    </pre>
                  </div>
                  <div>
                    <div className="mb-2 text-xs text-muted">stderr tail</div>
                    <pre className="scrollbar-thin max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-xl border border-line/70 bg-panel p-3 font-mono text-xs text-[#ced9e5]">
                      {selectedJob.stderrTail.join("\n") || "无 stderr"}
                    </pre>
                  </div>
                  <div>
                    <div className="mb-2 text-xs text-muted">events</div>
                    <div className="space-y-2">
                      {selectedJob.events.slice(-8).map((event) => (
                        <div key={`${event.time}_${event.label}`} className="rounded-xl border border-line/70 bg-panel px-3 py-2 text-xs text-muted">
                          <div className="font-mono">{new Date(event.time).toLocaleTimeString("zh-CN")}</div>
                          <div className="mt-1 text-ink">{event.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
            </div>
            ) : null}
            <div className="rounded-2xl border border-line bg-[#0b1524] p-4">
              <div className="text-sm font-semibold text-ink">选中文件</div>
              {selectedFile ? (
                <>
                  <div className="mt-3 font-mono text-xs text-muted break-all">{selectedFile.path}</div>
                  <pre className="scrollbar-thin mt-3 max-h-[32rem] overflow-auto rounded-xl border border-line/70 bg-panel p-3 font-mono text-xs text-[#ced9e5]">
                    {selectedFile.content}
                  </pre>
                </>
              ) : (
                <div className="mt-3 text-sm text-muted">点击结果 JSON、报告原文或 testcase 路径后会显示内容。</div>
              )}
            </div>
          </div>
          </>
          )}
        </aside>
      </div>
    </div>
  );
}
