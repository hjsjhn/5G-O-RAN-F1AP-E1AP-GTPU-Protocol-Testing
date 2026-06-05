import fg from "fast-glob";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type {
  ContainerState,
  FileDocument,
  FlowSummary,
  IssueCaseSummary,
  IssueRunInfo,
  MarkdownDocument,
  ProtocolReplayCard,
  ReportItem,
  SystemStatus
} from "../shared/types.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const dashboardRoot = path.resolve(__dirname, "../..");
export const repoRoot = path.resolve(dashboardRoot, "..");

export const containerNames = [
  "nrf",
  "smf",
  "amf",
  "upf",
  "srsran_cu_cp",
  "srsran_cu_up",
  "srsran_du"
];

const reportRegistry: Array<Omit<ReportItem, "kind"> & { kind?: ReportItem["kind"] }> = [
  {
    slug: "progress",
    title: "项目进度",
    path: "docs/progress.md",
    kind: "doc"
  },
  {
    slug: "implementation",
    title: "实施计划",
    path: "IMPLEMENTATION.md",
    kind: "doc"
  },
  {
    slug: "issue-report",
    title: "Open5GS Issue 报告",
    path: "reports/testcase_reports/stage5c6-open5gs-issue-report.md",
    kind: "report"
  },
  {
    slug: "parse-report",
    title: "协议解析报告",
    path: "reports/testcase_reports/stage4-parse-report.md",
    kind: "report"
  },
  {
    slug: "encoding-report",
    title: "离线编码报告",
    path: "reports/testcase_reports/stage5c3-offline-encoding-report.md",
    kind: "report"
  },
  {
    slug: "peer-report",
    title: "对端验证报告",
    path: "reports/testcase_reports/stage5c4-peer-validation-report.md",
    kind: "report"
  },
  {
    slug: "flow-report",
    title: "完整 UE Flow 报告",
    path: "reports/testcase_reports/stage5c5-complete-flow-report.md",
    kind: "report"
  }
];

const protocolReplayCards: ProtocolReplayCard[] = [
  {
    id: "parse",
    title: "协议解析与结构化 JSON",
    description: "展示 F1AP/E1AP/XnAP/GTP-U 的结构化解析结果和验收证据。",
    requirement: "F1AP/E1AP/XnAP/GTP-U JSON parsing",
    path: "reports/testcase_reports/stage4-parse-report.md"
  },
  {
    id: "encoding",
    title: "离线可逆编码",
    description: "展示 JSON testcase 到 payload、pcap、tshark 校验的完整链路。",
    requirement: "5+ control messages re-encoded",
    path: "reports/testcase_reports/stage5c3-offline-encoding-report.md"
  },
  {
    id: "peer",
    title: "真实对端验证",
    description: "展示 F1AP/E1AP 同一 payload 进入真实对端组件的验证结果。",
    requirement: "GTP-U pcap/live replay",
    path: "reports/testcase_reports/stage5c4-peer-validation-report.md"
  },
  {
    id: "flow",
    title: "完整 UE Flow",
    description: "展示注册、PDU Session、Inactivity Release 的自动化结果。",
    requirement: "UE flows",
    path: "reports/testcase_reports/stage5c5-complete-flow-report.md"
  }
];

async function readJson<T>(absolutePath: string): Promise<T | null> {
  try {
    const content = await fs.readFile(absolutePath, "utf-8");
    return JSON.parse(content) as T;
  } catch {
    return null;
  }
}

async function fileExists(absolutePath: string): Promise<boolean> {
  try {
    await fs.access(absolutePath);
    return true;
  } catch {
    return false;
  }
}

export function resolveRepoPath(relativePath: string): string {
  return path.resolve(repoRoot, relativePath);
}

export async function runRepoCommand(command: string): Promise<{
  stdout: string;
  stderr: string;
  exitCode: number;
}> {
  const { spawn } = await import("node:child_process");
  return new Promise((resolve) => {
    const child = spawn("bash", ["-lc", command], {
      cwd: repoRoot,
      env: process.env
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("close", (code) => {
      resolve({
        stdout,
        stderr,
        exitCode: code ?? 0
      });
    });
  });
}

function tailLines(text: string, max = 20): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter(Boolean)
    .slice(-max);
}

async function getBranchName(): Promise<string> {
  const result = await runRepoCommand("git rev-parse --abbrev-ref HEAD");
  return result.stdout.trim() || "unknown";
}

async function getOpen5gsImage(): Promise<string> {
  const result = await runRepoCommand("docker inspect nrf --format '{{.Config.Image}}'");
  return result.stdout.trim() || "unknown";
}

async function inspectContainers(): Promise<ContainerState[]> {
  const command = containerNames
    .map(
      (name) =>
        `docker inspect ${name} --format '{{.Name}}|{{.State.Status}}|{{.State.Running}}|{{.State.ExitCode}}' 2>/dev/null || echo '/${name}|missing|false|0'`
    )
    .join("\n");
  const result = await runRepoCommand(command);
  return tailLines(result.stdout, 50).map((line) => {
    const [rawName, status, running, exitCode] = line.split("|");
    return {
      name: rawName.replace(/^\//, ""),
      status,
      running: running === "true",
      exitCode: Number.isFinite(Number(exitCode)) ? Number(exitCode) : null
    };
  });
}

export async function getSystemStatus(lastRestoreState: "unknown" | "ok" | "failed", currentMutatingJob?: SystemStatus["currentMutatingJob"]): Promise<SystemStatus> {
  const [health, image, branch, containers] = await Promise.all([
    runRepoCommand("./scripts/env/check_core_ready.sh"),
    getOpen5gsImage(),
    getBranchName(),
    inspectContainers()
  ]);
  const stdout = tailLines(health.stdout, 20);
  const stderr = tailLines(health.stderr, 20);
  return {
    checkedAt: new Date().toISOString(),
    baseline: {
      ready: health.exitCode === 0,
      summary: stdout.at(-1) ?? stderr.at(-1) ?? "无输出",
      stdout,
      stderr,
      exitCode: health.exitCode
    },
    open5gsImage: image,
    branch,
    lastRestoreState,
    containers,
    currentMutatingJob: currentMutatingJob ?? null
  };
}

function summarizeMutation(caseData: Record<string, unknown>): { mutation: string; request: string } {
  const protocol = String(caseData.protocol ?? "");
  if (protocol === "SBI") {
    const target = caseData.target as Record<string, unknown>;
    const query = (caseData.query ?? {}) as Record<string, unknown>;
    const body = (caseData.body ?? {}) as Record<string, unknown>;
    const mutation = query["requester-features"]
      ? `requester-features=${String(query["requester-features"]).slice(0, 20)}...`
      : Object.keys(body)
          .map((key) => `${key}=${typeof body[key] === "object" ? "[object]" : String(body[key])}`)
          .join(", ");
    return {
      mutation,
      request: `${target.method ?? "GET"} ${target.path ?? ""}`
    };
  }
  if (protocol === "PFCP") {
    const mutation = caseData.mutation as Record<string, unknown>;
    return {
      mutation: `${mutation.group_ie ?? "PFCP"} far_id=${mutation.far_id ?? ""}`,
      request: `${mutation.pfcp_message ?? "PFCP"} -> ${String((caseData.transport as Record<string, unknown>).target_host ?? "upf")}`
    };
  }
  const sequence = caseData.sequence as Record<string, unknown>;
  return {
    mutation: `iterations=${sequence.iterations ?? "?"}, command=${sequence.deregister_command ?? ""}`,
    request: "UERANSIM deregistration / re-registration"
  };
}

function preferredIssueOrder(caseData: Record<string, unknown>): number {
  const issueUrl = String(caseData.issue ?? "");
  const fixUrl = String(caseData.fix ?? "");
  const combined = `${issueUrl} ${fixUrl} ${String(caseData.id ?? "")}`;
  if (combined.includes("4333") || combined.includes("4263")) {
    return 0;
  }
  if (combined.includes("4532")) {
    return 1;
  }
  if (combined.includes("4327")) {
    return 2;
  }
  if (combined.includes("4289") || combined.includes("4209")) {
    return 3;
  }
  return 99;
}

export async function getIssueCases(): Promise<IssueCaseSummary[]> {
  const issueFiles = await fg("tests/replay/open5gs_issues/*.json", {
    cwd: repoRoot,
    absolute: true
  });
  const resultFiles = await fg("json/replay_results/stage5c6/**/*.json", {
    cwd: repoRoot,
    absolute: true
  });

  const resultsByCase = new Map<
    string,
    {
      latestLiveRun?: IssueRunInfo;
      latestDryRun?: IssueRunInfo;
    }
  >();

  for (const resultFile of resultFiles) {
    const data = await readJson<Record<string, unknown>>(resultFile);
    if (!data || typeof data.case_id !== "string") {
      continue;
    }
    const mode = String(data.mode ?? "");
    const normalizedMode = mode.toLowerCase();
    const targetKey = normalizedMode.includes("dry") ? "latestDryRun" : "latestLiveRun";
    const generatedAt = String(data.generated_at ?? "");
    const current = resultsByCase.get(data.case_id) ?? {};
    const existing = current[targetKey];
    if (!existing || generatedAt > String(existing.generatedAt ?? "")) {
      current[targetKey] = {
        path: resultFile,
        mode,
        classification: typeof data.classification === "string" ? String(data.classification) : undefined,
        baselineRestored: Boolean((data.baseline_restore as { restored?: boolean } | undefined)?.restored),
        generatedAt,
        result: data
      };
      resultsByCase.set(data.case_id, current);
    }
  }

  const cases: IssueCaseSummary[] = [];
  for (const issueFile of issueFiles) {
    const caseData = await readJson<Record<string, unknown>>(issueFile);
    if (!caseData || typeof caseData.id !== "string") {
      continue;
    }
    const resultInfo = resultsByCase.get(caseData.id);
    const displayResult = resultInfo?.latestLiveRun ?? resultInfo?.latestDryRun;
    cases.push({
      id: caseData.id,
      title: String(caseData.title ?? caseData.id),
      component: String(caseData.component ?? ""),
      protocol: String(caseData.protocol ?? ""),
      issue: String(caseData.issue ?? ""),
      fix: String(caseData.fix ?? ""),
      casePath: issueFile,
      resultPath: displayResult?.path,
      classification: displayResult?.classification,
      baselineRestored: displayResult?.baselineRestored,
      displayMode: displayResult?.mode,
      latestLiveRun: resultInfo?.latestLiveRun,
      latestDryRun: resultInfo?.latestDryRun,
      summary: summarizeMutation(caseData),
      result: displayResult?.result,
      caseData
    });
  }

  return cases.sort((left, right) => {
    const orderDiff = preferredIssueOrder(left.caseData) - preferredIssueOrder(right.caseData);
    if (orderDiff !== 0) {
      return orderDiff;
    }
    return left.title.localeCompare(right.title);
  });
}

function labelForFlow(flow: string): string {
  return flow === "registration_release" ? "Registration + Inactivity Release" : "Registration + PDU Session";
}

export async function getLatestFlows(): Promise<FlowSummary[]> {
  const files = await fg("json/flow_results/**/result.json", {
    cwd: repoRoot,
    absolute: true
  });
  const latest = new Map<string, { path: string; data: Record<string, unknown>; generatedAt: string }>();

  for (const file of files) {
    const data = await readJson<Record<string, unknown>>(file);
    if (!data || typeof data.flow !== "string") {
      continue;
    }
    const flow = data.flow;
    const generatedAt = String(data.generated_at ?? "");
    const existing = latest.get(flow);
    if (!existing || generatedAt > existing.generatedAt) {
      latest.set(flow, { path: file, data, generatedAt });
    }
  }

  const flows = ["registration_pdu_session", "registration_release"].map<FlowSummary>((flow) => {
    const current = latest.get(flow);
    if (!current) {
      return {
        flow,
        label: labelForFlow(flow),
        status: "missing"
      };
    }
    return {
      flow,
      label: labelForFlow(flow),
      status: "present",
      result: String(current.data.result ?? ""),
      runId: String(current.data.run_id ?? ""),
      generatedAt: String(current.data.generated_at ?? ""),
      resultPath: current.path,
      artifacts: (current.data.artifacts as Record<string, string> | undefined) ?? {},
      counts: (current.data.counts as Record<string, number> | undefined) ?? {},
      timeline: (current.data.timeline as Array<Record<string, unknown>> | undefined) ?? [],
      checks: (current.data.checks as Array<Record<string, unknown>> | undefined) ?? []
    };
  });

  return flows;
}

export function getProtocolReplayCards(): ProtocolReplayCard[] {
  return protocolReplayCards.map((item) => ({
    ...item,
    path: resolveRepoPath(item.path)
  }));
}

export async function getReports(): Promise<ReportItem[]> {
  const items: ReportItem[] = [];
  for (const entry of reportRegistry) {
    const absolutePath = resolveRepoPath(entry.path);
    if (await fileExists(absolutePath)) {
      items.push({
        slug: entry.slug,
        title: entry.title,
        path: absolutePath,
        kind: entry.kind ?? "report"
      });
    }
  }
  return items;
}

export async function readMarkdownBySlug(slug: string): Promise<MarkdownDocument | null> {
  const item = reportRegistry.find((entry) => entry.slug === slug);
  if (!item) {
    return null;
  }
  const absolutePath = resolveRepoPath(item.path);
  if (!(await fileExists(absolutePath))) {
    return null;
  }
  return {
    slug,
    title: item.title,
    path: absolutePath,
    content: await fs.readFile(absolutePath, "utf-8")
  };
}

export async function readWhitelistedFile(targetPath: string): Promise<FileDocument | null> {
  const whitelist = new Set<string>();

  for (const report of await getReports()) {
    whitelist.add(report.path);
  }

  for (const issue of await getIssueCases()) {
    whitelist.add(issue.casePath);
    if (issue.resultPath) {
      whitelist.add(issue.resultPath);
    }
    if (issue.latestLiveRun?.path) {
      whitelist.add(issue.latestLiveRun.path);
    }
    if (issue.latestDryRun?.path) {
      whitelist.add(issue.latestDryRun.path);
    }
  }

  for (const flow of await getLatestFlows()) {
    if (flow.resultPath) {
      whitelist.add(flow.resultPath);
    }
    for (const artifact of Object.values(flow.artifacts ?? {})) {
      whitelist.add(path.resolve(repoRoot, artifact));
    }
  }

  const absolutePath = path.resolve(targetPath);
  if (!whitelist.has(absolutePath)) {
    return null;
  }
  return {
    path: absolutePath,
    content: await fs.readFile(absolutePath, "utf-8")
  };
}
