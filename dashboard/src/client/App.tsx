import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import type {
  FileDocument,
  FlowSummary,
  IssueCaseSummary,
  JobSummary,
  MarkdownDocument,
  NavKey,
  ProtocolReplayCard,
  ReportItem,
  SystemStatus
} from "../shared/types";

const navItems: Array<{ key: NavKey; label: string; description: string }> = [
  { key: "overview", label: "系统总览", description: "baseline 健康、容器状态、恢复入口" },
  { key: "issues", label: "Issue 测试", description: "Open5GS issue-driven testcase" },
  { key: "ue-flow", label: "UE 流程", description: "完整注册与释放流程结果" },
  { key: "protocol-replay", label: "协议 / 回放", description: "协议解析、编码与验证报告" },
  { key: "reports", label: "报告", description: "进度、实施计划与阶段报告" }
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
    <div className="min-w-0 overflow-hidden rounded-2xl border border-line bg-panel/90 p-4 shadow-panel">
      <div className="text-xs uppercase tracking-[0.2em] text-muted">{props.title}</div>
      <div className={`mt-3 break-all text-lg font-semibold ${props.tone ?? "text-ink"}`}>{props.value}</div>
      {props.detail ? <div className="mt-2 break-all text-sm text-muted">{props.detail}</div> : null}
    </div>
  );
}

function KV(props: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid gap-1 rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2">
      <div className="text-xs text-muted">{props.label}</div>
      <div className="text-sm text-ink">{props.value}</div>
    </div>
  );
}

export function App() {
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
  const [selectedFile, setSelectedFile] = useState<FileDocument | null>(null);
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState<string>("");

  const currentIssue = useMemo(
    () => issues.find((item) => item.id === selectedIssueId) ?? issues[0] ?? null,
    [issues, selectedIssueId]
  );

  const currentFlow = useMemo(
    () => flows.find((item) => item.flow === "registration_pdu_session") ?? flows[0] ?? null,
    [flows]
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
      if (!selectedIssueId && issueData[0]) {
        setSelectedIssueId(issueData[0].id);
      }
      if (!selectedJob && jobData[0]) {
        setSelectedJob(jobData[0]);
      } else if (selectedJob) {
        const current = jobData.find((job) => job.id === selectedJob.id);
        if (current) {
          setSelectedJob(current);
        } else {
          setSelectedJob(jobData[0] ?? null);
        }
      }
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
    if (activeNav === "reports" && selectedReportSlug) {
      void loadReport(selectedReportSlug);
    }
  }, [activeNav, selectedReportSlug]);

  async function runRestore() {
    setBusy("restore");
    try {
      const job = await getJson<JobSummary>("/api/system/restore", { method: "POST" });
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
      setSelectedJob(job);
      setActiveNav("issues");
      await loadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "执行失败");
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
        <div className="grid gap-4 md:grid-cols-3">
          <SummaryCard
            title="Baseline"
            value={system.baseline.ready ? "READY" : "FAIL"}
            detail={system.baseline.summary}
            tone={system.baseline.ready ? "text-accent" : "text-danger"}
          />
          <SummaryCard title="Open5GS Digest" value={system.open5gsImage} detail={`Branch: ${system.branch}`} />
          <SummaryCard
            title="Last Restore"
            value={system.lastRestoreState === "ok" ? "成功" : system.lastRestoreState === "failed" ? "失败" : "未运行"}
            detail={`更新于 ${new Date(system.checkedAt).toLocaleString("zh-CN")}`}
            tone={system.lastRestoreState === "failed" ? "text-danger" : system.lastRestoreState === "ok" ? "text-accent" : "text-ink"}
          />
        </div>
        <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
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
          description="读取 testcase JSON 和 stage5c6 结果，支持 dry-run 与 live-run。"
        />
        <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
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
                    label="执行 Dry-run"
                    onClick={() => void runIssue(currentIssue.id, false)}
                    disabled={busy !== "" || system?.currentMutatingJob?.status === "restore_failed"}
                  />
                  <ActionButton
                    label="执行 Live run"
                    onClick={() => void runIssue(currentIssue.id, true)}
                    disabled={busy !== "" || Boolean(system?.currentMutatingJob)}
                    tone="danger"
                  />
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                <KV label="Issue URL" value={<a className="text-accent" href={currentIssue.issue} target="_blank" rel="noreferrer">{currentIssue.issue}</a>} />
                <KV label="Fix / 边界" value={<span className="break-all font-mono text-xs">{currentIssue.fix}</span>} />
                <KV label="Mutation" value={<span className="font-mono text-xs">{currentIssue.summary.mutation}</span>} />
                <KV label="Request Summary" value={<span className="font-mono text-xs">{currentIssue.summary.request}</span>} />
                <KV label="Testcase JSON" value={pathTag(currentIssue.casePath)} />
                <KV label="默认展示结果" value={<span className="font-mono text-xs">{currentIssue.displayMode ?? "无"}</span>} />
                <KV label="Latest Live Result JSON" value={pathTag(currentIssue.latestLiveRun?.path)} />
                <KV label="Latest Dry-run Result JSON" value={pathTag(currentIssue.latestDryRun?.path)} />
              </div>
              {currentIssue.result ? (
                <div className="grid gap-3 md:grid-cols-2">
                  <KV label="classification" value={<span className={`font-mono ${classForStatus(String(currentIssue.result.classification ?? ""))}`}>{String(currentIssue.result.classification ?? "-")}</span>} />
                  <KV
                    label="baseline_restore.restored"
                    value={
                      <span className={`font-mono ${currentIssue.result.classification === "DRY_RUN" ? "text-muted" : currentIssue.baselineRestored ? "text-accent" : "text-danger"}`}>
                        {currentIssue.result.classification === "DRY_RUN" ? "N/A (DRY_RUN)" : String(currentIssue.baselineRestored)}
                      </span>
                    }
                  />
                  <KV label="target_before" value={<span className="font-mono text-xs">{`${String((currentIssue.result.target_before as { status?: string } | undefined)?.status ?? "-")} -> ${String((currentIssue.result.target_after as { status?: string } | undefined)?.status ?? "-")}`}</span>} />
                  <KV label="restart_count_delta" value={<span className="font-mono text-xs">{String(currentIssue.result.restart_count_delta ?? 0)}</span>} />
                  <KV label="request_summary" value={<span className="font-mono text-xs break-all">{JSON.stringify(currentIssue.result.request_summary ?? {}, null, 0)}</span>} />
                  <KV label="log delta" value={<span className="font-mono text-xs break-all">{JSON.stringify(currentIssue.result.log_delta ?? currentIssue.result[`${currentIssue.component}_log_delta`] ?? {}, null, 0)}</span>} />
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <ActionButton label="查看 Testcase JSON" onClick={() => void openFile(currentIssue.casePath)} />
                <ActionButton label="查看 Live 结果" onClick={() => void openFile(currentIssue.latestLiveRun?.path)} disabled={!currentIssue.latestLiveRun?.path} />
                <ActionButton label="查看 Dry-run 结果" onClick={() => void openFile(currentIssue.latestDryRun?.path)} disabled={!currentIssue.latestDryRun?.path} />
              </div>
              {(currentIssue.id.includes("4532") && currentIssue.result) ? (
                <div className="rounded-2xl border border-danger/40 bg-danger/10 p-4">
                  <div className="text-sm font-semibold text-danger">#4532 关键展示证据</div>
                  <div className="mt-3 grid gap-2 text-sm text-ink">
                    <div><span className="text-muted">classification:</span> <span className="font-mono text-danger">{String(currentIssue.result.classification ?? "-")}</span></div>
                    <div><span className="text-muted">curl:</span> <span className="font-mono">exit {String((currentIssue.result.request as { curl_exit_code?: number } | undefined)?.curl_exit_code ?? "-")}, {String((currentIssue.result.request as { curl_stderr?: string } | undefined)?.curl_stderr ?? "-")}</span></div>
                    <div><span className="text-muted">smf:</span> <span className="font-mono">{`${String((currentIssue.result.target_before as { status?: string } | undefined)?.status ?? "-")} -> ${String((currentIssue.result.target_after as { status?: string } | undefined)?.status ?? "-")}`}</span></div>
                    <div><span className="text-muted">exit_code:</span> <span className="font-mono">{String((currentIssue.result.target_after as { exit_code?: number } | undefined)?.exit_code ?? "-")}</span></div>
                    <div><span className="text-muted">fatal:</span> <span className="font-mono text-xs break-all">{String(((currentIssue.result.smf_log_delta as { fatal_keyword_hits?: string[] } | undefined)?.fatal_keyword_hits ?? [])[0] ?? "-")}</span></div>
                    <div><span className="text-muted">baseline_restore.restored:</span> <span className="font-mono text-accent">{String((currentIssue.result.baseline_restore as { restored?: boolean } | undefined)?.restored ?? false)}</span></div>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  function renderFlows() {
    return (
      <div className="space-y-6">
        <SectionTitle title="UE Flow" description="展示最新 Registration + PDU Session 与 Registration + Inactivity Release 结果。" />
        <div className="grid gap-4 md:grid-cols-2">
          {flows.map((flow) => (
            <div key={flow.flow} className="rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-ink">{flow.label}</h3>
                <span className={`font-mono text-sm ${classForStatus(flow.result ?? flow.status)}`}>{flow.result ?? flow.status.toUpperCase()}</span>
              </div>
              <div className="mt-4 grid gap-3">
                <KV label="Run ID" value={<span className="font-mono text-xs">{flow.runId ?? "无"}</span>} />
                <KV label="Result JSON" value={pathTag(flow.resultPath)} />
                <KV label="Timeline Events" value={<span className="font-mono">{String(flow.counts?.timeline_events ?? "-")}</span>} />
                <KV label="Control Messages" value={<span className="font-mono">{String(flow.counts?.control_messages ?? "-")}</span>} />
                <KV label="Logs" value={pathTag(flow.artifacts?.logs)} />
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <ActionButton label="查看结果 JSON" onClick={() => void openFile(flow.resultPath)} disabled={!flow.resultPath} />
                <ActionButton label="查看 logs 路径" onClick={() => void openFile(flow.artifacts?.logs)} disabled={!flow.artifacts?.logs} />
                <ActionButton label="查看历史结果" disabled={!flow.resultPath} onClick={() => void openFile(flow.resultPath)} />
              </div>
              <div className="mt-4 rounded-xl border border-line/70 bg-[#0b1524] p-3">
                <div className="mb-2 text-xs text-muted">关键检查</div>
                <div className="grid gap-2">
                  {(flow.checks ?? []).slice(0, 6).map((check) => (
                    <div key={String(check.name)} className="flex items-start justify-between gap-3 text-sm">
                      <div className="text-ink">{String(check.name)}</div>
                      <div className={Boolean(check.passed) ? "text-accent" : "text-danger"}>{Boolean(check.passed) ? "PASS" : "MISS"}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
        {currentFlow?.timeline?.length ? (
          <div className="rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
            <div className="mb-4 text-lg font-semibold text-ink">时间线预览</div>
            <div className="space-y-2">
              {currentFlow.timeline.slice(0, 12).map((event, index) => (
                <div key={`${String(event.protocol)}_${index}`} className="grid grid-cols-[0.8fr_1fr_1.2fr] gap-3 rounded-xl border border-line/70 bg-[#0b1524] px-3 py-2 text-sm">
                  <div className="font-mono text-muted">{String(event.protocol)}</div>
                  <div className="text-ink">{String(event.message)}</div>
                  <div className="text-muted">{String(event.direction)}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  function renderProtocolReplay() {
    return (
      <div className="space-y-6">
        <SectionTitle title="协议 / 回放" description="将阶段报告映射到课程验收要求。" />
        <div className="grid gap-4 md:grid-cols-2">
          {cards.map((card) => (
            <div key={card.id} className="rounded-2xl border border-line bg-panel/95 p-5 shadow-panel">
              <div className="text-sm uppercase tracking-[0.2em] text-muted">{card.requirement}</div>
              <h3 className="mt-3 text-lg font-semibold text-ink">{card.title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted">{card.description}</p>
              <div className="mt-4 rounded-xl border border-line/70 bg-[#0b1524] p-3 text-xs text-muted">
                {card.path}
              </div>
              <div className="mt-4 flex gap-2">
                <ActionButton label="打开报告" onClick={() => { setActiveNav("reports"); const slug = reports.find((item) => item.path === card.path)?.slug ?? "progress"; void loadReport(slug); }} />
                <ActionButton label="查看原文" onClick={() => void openFile(card.path)} />
              </div>
            </div>
          ))}
        </div>
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
      <div className="mx-auto grid min-h-screen max-w-[1800px] grid-cols-1 gap-4 p-4 xl:grid-cols-[250px_minmax(0,1fr)_420px]">
        <aside className="rounded-[28px] border border-line bg-panel/90 p-4 shadow-panel">
          <div className="rounded-2xl border border-line/70 bg-[#0b1524] p-4">
            <div className="text-xs uppercase tracking-[0.3em] text-muted">5G O-RAN</div>
            <div className="mt-2 text-xl font-semibold">测试控制台</div>
            <div className="mt-2 text-sm text-muted">实验控制台，不是宣传页。</div>
          </div>
          <nav className="mt-4 space-y-2">
            {navItems.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setActiveNav(item.key)}
                className={`w-full rounded-2xl border p-4 text-left transition ${
                  activeNav === item.key ? "border-accent bg-[#11253a]" : "border-line bg-[#0b1524] hover:bg-[#122137]"
                }`}
              >
                <div className="text-sm font-semibold text-ink">{item.label}</div>
                <div className="mt-1 text-xs text-muted">{item.description}</div>
              </button>
            ))}
          </nav>
        </aside>

        <main className="space-y-4">
          <div className="rounded-[28px] border border-line bg-panel/90 p-4 shadow-panel">
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <SummaryCard
                title="Baseline 状态"
                value={system?.baseline.ready ? "READY" : "FAIL"}
                detail={system?.baseline.summary ?? "加载中"}
                tone={system?.baseline.ready ? "text-accent" : "text-danger"}
              />
              <SummaryCard title="当前 Branch / Open5GS" value={system?.branch ?? "loading"} detail={system?.open5gsImage ?? "loading"} />
              <SummaryCard
                title="当前任务"
                value={system?.currentMutatingJob?.stepName ?? "空闲"}
                detail={system?.currentMutatingJob ? `${formatJobStatus(system.currentMutatingJob.status)} / ${formatSeconds(system.currentMutatingJob.elapsedSeconds)}` : "当前没有 mutating job"}
                tone={system?.currentMutatingJob ? "text-warn" : "text-accent"}
              />
            </div>
            {error ? <div className="mt-4 rounded-2xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</div> : null}
          </div>

          <div className="rounded-[28px] border border-line bg-panel/90 p-6 shadow-panel">
            {activeNav === "overview" ? renderOverview() : null}
            {activeNav === "issues" ? renderIssues() : null}
            {activeNav === "ue-flow" ? renderFlows() : null}
            {activeNav === "protocol-replay" ? renderProtocolReplay() : null}
            {activeNav === "reports" ? renderReports() : null}
          </div>
        </main>

        <aside className="min-w-0 rounded-[28px] border border-line bg-panel/90 p-4 shadow-panel">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-ink">日志与结果</div>
              <div className="mt-1 text-xs text-muted">右侧固定显示最近任务和当前选中文件。</div>
            </div>
            {selectedJob?.abortable ? (
              <ActionButton
                label="中止并恢复"
                tone="danger"
                onClick={() => void abortAndRestore()}
                disabled={busy === "abort"}
              />
            ) : null}
          </div>
          <div className="scrollbar-thin space-y-4 overflow-y-auto pr-1" style={{ maxHeight: "calc(100vh - 120px)" }}>
            <div className="rounded-2xl border border-line bg-[#0b1524] p-4">
              <div className="text-sm font-semibold text-ink">当前任务</div>
              {selectedJob ? (
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
              ) : (
                <div className="mt-3 text-sm text-muted">暂无任务。</div>
              )}
            </div>
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
        </aside>
      </div>
    </div>
  );
}
