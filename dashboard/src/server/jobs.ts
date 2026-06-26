import fs from "node:fs/promises";
import path from "node:path";
import { spawn, type ChildProcess } from "node:child_process";
import type { JobSummary, JobStatus } from "../shared/types.js";
import { repoRoot, resolveRepoPath, runRepoCommand } from "./data.js";

type JobType = JobSummary["type"];

type MutableJob = JobSummary & {
  child?: ChildProcess;
  liveCaseId?: string;
  resultFilePath?: string;
  timers: NodeJS.Timeout[];
  aborted: boolean;
  settled: boolean;
  stageStartedAt: string;
  frozenElapsedSeconds?: number;
  frozenStageElapsedSeconds?: number;
  frozenIdleSeconds?: number;
};

type Stage = {
  index: number;
  total: number;
  name: string;
  label: string;
  status?: JobStatus;
};

function createId(prefix: string): string {
  return `${prefix}_${Date.now()}`;
}

function tailPush(target: string[], lines: string[]): string[] {
  const next = [...target, ...lines.filter(Boolean)];
  return next.slice(-30);
}

function splitLines(chunk: string): string[] {
  return chunk
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter(Boolean);
}

function elapsedSecondsBetween(from: string, to = new Date().toISOString()): number {
  return Math.max(0, Math.floor((new Date(to).getTime() - new Date(from).getTime()) / 1000));
}

function newJob(type: JobType, title: string, mutating: boolean): MutableJob {
  const now = new Date().toISOString();
  return {
    id: createId(type),
    type,
    title,
    mutating,
    status: "queued",
    startedAt: now,
    stepIndex: 0,
    stepTotal: 1,
    stepName: "等待开始",
    progressLabel: "等待执行。",
    elapsedSeconds: 0,
    stageElapsedSeconds: 0,
    stdoutTail: [],
    stderrTail: [],
    events: [{ time: now, label: "已加入队列" }],
    timers: [],
    aborted: false,
    settled: false,
    stageStartedAt: now
  };
}

export class JobManager {
  private jobs = new Map<string, MutableJob>();
  private currentMutatingJobId: string | null = null;
  private lastRestoreState: "unknown" | "ok" | "failed" = "unknown";

  getLastRestoreState(): "unknown" | "ok" | "failed" {
    return this.lastRestoreState;
  }

  getCurrentMutatingJob(): JobSummary | null {
    if (!this.currentMutatingJobId) {
      return null;
    }
    const job = this.jobs.get(this.currentMutatingJobId);
    return job ? this.snapshot(job) : null;
  }

  getJob(id: string): JobSummary | null {
    const job = this.jobs.get(id);
    return job ? this.snapshot(job) : null;
  }

  listJobs(): JobSummary[] {
    return [...this.jobs.values()]
      .sort((left, right) => right.startedAt.localeCompare(left.startedAt))
      .map((job) => this.snapshot(job));
  }

  private snapshot(job: MutableJob): JobSummary {
    const currentElapsed = job.finishedAt
      ? (job.frozenElapsedSeconds ?? elapsedSecondsBetween(job.startedAt, job.finishedAt))
      : elapsedSecondsBetween(job.startedAt);
    const currentStageElapsed = job.finishedAt
      ? (job.frozenStageElapsedSeconds ?? currentElapsed)
      : elapsedSecondsBetween(job.stageStartedAt);
    const currentIdle = job.finishedAt
      ? (job.frozenIdleSeconds ?? 0)
      : job.lastLogAt
        ? elapsedSecondsBetween(job.lastLogAt)
        : currentElapsed;

    return {
      id: job.id,
      type: job.type,
      status: job.status,
      mutating: job.mutating,
      title: job.title,
      startedAt: job.startedAt,
      finishedAt: job.finishedAt,
      stepIndex: job.stepIndex,
      stepTotal: job.stepTotal,
      stepName: job.stepName,
      progressLabel: job.progressLabel,
      elapsedSeconds: currentElapsed,
      stageElapsedSeconds: currentStageElapsed,
      stdoutTail: [...job.stdoutTail],
      stderrTail: [...job.stderrTail],
      events: [...job.events],
      resultPath: job.resultPath,
      resultSummary: job.resultSummary,
      error: job.error,
      lastLogAt: job.lastLogAt,
      idleSeconds: currentIdle,
      abortable: Boolean(job.child && !job.settled && (job.status === "running" || job.status === "collecting_results"))
    };
  }

  private markStage(job: MutableJob, stage: Stage): void {
    const now = new Date().toISOString();
    job.stepIndex = stage.index;
    job.stepTotal = stage.total;
    job.stepName = stage.name;
    job.progressLabel = stage.label;
    job.stageStartedAt = now;
    if (stage.status) {
      job.status = stage.status;
    } else if (job.status === "queued") {
      job.status = "running";
    }
    job.events.push({
      time: now,
      label: `阶段：${stage.name}`
    });
  }

  private note(job: MutableJob, label: string): void {
    job.events.push({
      time: new Date().toISOString(),
      label
    });
  }

  private setLogs(job: MutableJob, stream: "stdoutTail" | "stderrTail", chunk: string): void {
    const lines = splitLines(chunk);
    if (!lines.length) {
      return;
    }
    job[stream] = tailPush(job[stream], lines);
    job.lastLogAt = new Date().toISOString();
  }

  private appendCommandOutput(job: MutableJob, stdout: string, stderr: string): void {
    this.setLogs(job, "stdoutTail", stdout);
    this.setLogs(job, "stderrTail", stderr);
  }

  private clearTimers(job: MutableJob): void {
    for (const timer of job.timers) {
      clearTimeout(timer);
    }
    job.timers = [];
  }

  private scheduleStages(job: MutableJob, stages: Array<{ afterMs: number; stage: Stage }>): void {
    for (const entry of stages) {
      job.timers.push(
        setTimeout(() => {
          if (!job.settled && !job.aborted && (job.status === "running" || job.status === "queued")) {
            this.markStage(job, entry.stage);
          }
        }, entry.afterMs)
      );
    }
  }

  private startProcess(job: MutableJob, command: string): Promise<number> {
    job.status = "running";
    return new Promise((resolve, reject) => {
      const child = spawn("bash", ["-lc", command], {
        cwd: repoRoot,
        env: process.env,
        detached: true
      });
      job.child = child;
      child.stdout.on("data", (chunk) => this.setLogs(job, "stdoutTail", chunk.toString()));
      child.stderr.on("data", (chunk) => this.setLogs(job, "stderrTail", chunk.toString()));
      child.on("error", (error) => {
        job.child = undefined;
        reject(error);
      });
      child.on("close", (code) => {
        job.child = undefined;
        resolve(code ?? 0);
      });
    });
  }

  private async safeReadJson(resultPath?: string): Promise<Record<string, unknown> | undefined> {
    if (!resultPath) {
      return undefined;
    }
    try {
      const content = await fs.readFile(resultPath, "utf-8");
      return JSON.parse(content) as Record<string, unknown>;
    } catch {
      return undefined;
    }
  }

  private buildCompletionLabel(status: JobStatus, resultSummary?: Record<string, unknown>, error?: string, aborted?: boolean): string {
    const classification = typeof resultSummary?.classification === "string" ? String(resultSummary.classification) : "";
    const resultValue = typeof resultSummary?.result === "string" ? String(resultSummary.result) : "";
    const prefix =
      status === "completed"
        ? aborted
          ? "任务已中止并完成恢复。"
          : "任务已完成。"
        : status === "restore_failed"
          ? "任务结束，但 baseline 恢复失败。"
          : aborted
            ? "任务已中止，结果包含失败。"
            : "任务已完成，但结果包含失败。";
    const details = [classification, resultValue, error].filter(Boolean).join(" / ");
    return details ? `${prefix} ${details}` : prefix;
  }

  private finalizeJob(
    job: MutableJob,
    status: JobStatus,
    resultSummary?: Record<string, unknown>,
    overrideLabel?: string
  ): JobSummary {
    if (job.settled) {
      return this.snapshot(job);
    }

    const finishedAt = new Date().toISOString();
    job.settled = true;
    job.status = status;
    job.finishedAt = finishedAt;
    job.resultSummary = resultSummary ?? job.resultSummary;
    job.frozenElapsedSeconds = elapsedSecondsBetween(job.startedAt, finishedAt);
    job.frozenStageElapsedSeconds = elapsedSecondsBetween(job.stageStartedAt, finishedAt);
    job.frozenIdleSeconds = job.lastLogAt ? elapsedSecondsBetween(job.lastLogAt, finishedAt) : 0;
    job.stepIndex = job.stepTotal;
    job.stepName = "Completed";
    job.progressLabel = overrideLabel ?? this.buildCompletionLabel(status, job.resultSummary, job.error, job.aborted);
    job.events.push({
      time: finishedAt,
      label: `任务结束：${job.progressLabel}`
    });

    if (job.mutating && this.currentMutatingJobId === job.id) {
      this.currentMutatingJobId = null;
    }
    this.clearTimers(job);
    return this.snapshot(job);
  }

  private register(job: MutableJob): MutableJob {
    this.jobs.set(job.id, job);
    return job;
  }

  private ensureMutatingCapacity(): void {
    if (this.currentMutatingJobId) {
      throw new Error("当前已有会修改环境的任务在运行。");
    }
  }

  private async runRestoreSequence(job: MutableJob): Promise<boolean> {
    this.markStage(job, {
      index: 2,
      total: job.stepTotal,
      name: "Running restore_baseline.sh",
      label: "正在运行 restore_baseline.sh。",
      status: "restoring"
    });
    const restore = await runRepoCommand("./scripts/env/restore_baseline.sh");
    this.appendCommandOutput(job, restore.stdout, restore.stderr);

    this.markStage(job, {
      index: 3,
      total: job.stepTotal,
      name: "Running check_core_ready",
      label: "正在确认 baseline 已恢复。",
      status: "restoring"
    });
    const health = await runRepoCommand("./scripts/env/check_core_ready.sh");
    this.appendCommandOutput(job, health.stdout, health.stderr);

    this.markStage(job, {
      index: job.stepTotal,
      total: job.stepTotal,
      name: "Collecting restore status",
      label: "正在汇总恢复结果。",
      status: "collecting_results"
    });

    const restored = restore.exitCode === 0 && health.exitCode === 0;
    this.lastRestoreState = restored ? "ok" : "failed";
    if (!restored) {
      job.error = "Baseline restore failed";
      this.note(job, "恢复失败");
    } else {
      this.note(job, "baseline 已恢复");
    }
    return restored;
  }

  private async executeRestoreJob(job: MutableJob): Promise<void> {
    try {
      const restored = await this.runRestoreSequence(job);
      this.finalizeJob(job, restored ? "completed" : "restore_failed");
    } catch (error) {
      job.error = error instanceof Error ? error.message : "restore failed";
      this.finalizeJob(job, "restore_failed");
    }
  }

  private async executeIssueJob(
    job: MutableJob,
    options: {
      casePath: string;
      live: boolean;
    },
    resultFilePath: string
  ): Promise<void> {
    const command = [
      "python3 scripts/replay/run_open5gs_issue_tests.py",
      options.live ? "--live" : "",
      `--case ${JSON.stringify(path.relative(repoRoot, options.casePath))}`,
      `--output ${JSON.stringify(path.relative(repoRoot, resultFilePath))}`
    ]
      .filter(Boolean)
      .join(" ");

    try {
      const exitCode = await this.startProcess(job, command);
      if (job.aborted || job.settled) {
        return;
      }

      this.markStage(job, {
        index: job.stepTotal,
        total: job.stepTotal,
        name: "Collecting result",
        label: "正在校验结果文件。",
        status: "collecting_results"
      });
      this.note(job, "正在校验结果文件");

      const resultSummary = await this.safeReadJson(resultFilePath);
      const classification = typeof resultSummary?.classification === "string" ? String(resultSummary.classification) : "";
      const resultValue = typeof resultSummary?.result === "string" ? String(resultSummary.result) : "";
      const restoreOk = Boolean((resultSummary?.baseline_restore as { restored?: boolean } | undefined)?.restored);

      if (options.live) {
        this.lastRestoreState = restoreOk ? "ok" : "failed";
      }

      if (resultSummary) {
        job.resultPath = resultFilePath;
        job.resultSummary = resultSummary;
      }

      if (!resultSummary || !classification) {
        job.error = "结果文件不存在或结构不完整。";
        this.finalizeJob(job, options.live && !restoreOk ? "restore_failed" : "completed_with_failure");
        return;
      }

      const acceptedResult = options.live
        ? exitCode === 0 && resultValue === "PASS"
        : exitCode === 0 && (resultValue === "DRY-RUN" || classification === "DRY_RUN");

      const finalStatus = !acceptedResult
        ? options.live && !restoreOk
          ? "restore_failed"
          : "completed_with_failure"
        : options.live && !restoreOk
          ? "restore_failed"
          : "completed";

      if (!acceptedResult && !job.error) {
        job.error = `unexpected result: exit=${exitCode}, classification=${classification || "unknown"}, result=${resultValue || "unknown"}`;
      }

      this.finalizeJob(job, finalStatus);
    } catch (error) {
      if (job.aborted || job.settled) {
        return;
      }
      job.error = error instanceof Error ? error.message : "issue job failed";
      this.finalizeJob(job, "completed_with_failure");
    }
  }

  async abortAndRestore(id: string): Promise<JobSummary> {
    const job = this.jobs.get(id);
    if (!job) {
      throw new Error("任务不存在。");
    }
    if (!job.child || job.settled) {
      throw new Error("当前任务无法终止。");
    }

    job.aborted = true;
    this.note(job, "收到 Abort and restore 请求");
    try {
      process.kill(-job.child.pid!, "SIGTERM");
    } catch {
      this.note(job, "进程组终止失败，继续执行恢复");
    }

    this.markStage(job, {
      index: Math.max(1, job.stepTotal - 1),
      total: job.stepTotal,
      name: "Abort and restore",
      label: "正在终止任务并恢复 baseline。",
      status: "restoring"
    });

    try {
      const restored = await this.runRestoreSequence(job);
      return this.finalizeJob(job, restored ? "completed_with_failure" : "restore_failed");
    } catch (error) {
      job.error = error instanceof Error ? error.message : "abort restore failed";
      return this.finalizeJob(job, "restore_failed");
    }
  }

  async startRestoreJob(): Promise<JobSummary> {
    this.ensureMutatingCapacity();
    const job = this.register(newJob("restore", "恢复 baseline", true));
    this.currentMutatingJobId = job.id;
    this.markStage(job, {
      index: 1,
      total: 4,
      name: "Preparing restore",
      label: "准备执行 restore_baseline.sh。",
      status: "running"
    });

    void this.executeRestoreJob(job);
    return this.snapshot(job);
  }

  async startIssueJob(options: {
    caseId: string;
    casePath: string;
    live: boolean;
  }): Promise<JobSummary> {
    if (options.live) {
      this.ensureMutatingCapacity();
    }

    const title = `${options.live ? "Live run" : "Dry-run"} ${options.caseId}`;
    const job = this.register(newJob(options.live ? "issue_live_run" : "issue_dry_run", title, options.live));
    if (options.live) {
      this.currentMutatingJobId = job.id;
    }

    job.liveCaseId = options.caseId;
    const suffix = options.live ? "live" : "dry_run";
    const resultFilePath = resolveRepoPath(
      path.join("json/replay_results/stage5c6/dashboard", `${options.caseId}_${suffix}_${Date.now()}.json`)
    );
    job.resultFilePath = resultFilePath;

    if (options.live) {
      this.markStage(job, {
        index: 1,
        total: 6,
        name: "Checking baseline",
        label: "正在确认 baseline 当前健康。",
        status: "running"
      });
      this.scheduleStages(job, [
        {
          afterMs: 1500,
          stage: {
            index: 2,
            total: 6,
            name: "Sending mutation",
            label: "正在发送 mutation，请等待目标网元响应。"
          }
        },
        {
          afterMs: 5000,
          stage: {
            index: 3,
            total: 6,
            name: "Sampling target state",
            label: "正在采样目标容器状态和退出码。"
          }
        },
        {
          afterMs: 9000,
          stage: {
            index: 4,
            total: 6,
            name: "Collecting logs",
            label: "正在收集日志差异和结果文件。"
          }
        },
        {
          afterMs: 14000,
          stage: {
            index: 5,
            total: 6,
            name: "Restoring baseline",
            label: "脚本正在恢复 baseline。"
          }
        }
      ]);
    } else {
      this.markStage(job, {
        index: 1,
        total: 4,
        name: "Loading testcase",
        label: "正在解析 testcase。",
        status: "running"
      });
      this.scheduleStages(job, [
        {
          afterMs: 1000,
          stage: {
            index: 2,
            total: 4,
            name: "Sampling target state",
            label: "正在采样目标容器当前状态。"
          }
        },
        {
          afterMs: 2200,
          stage: {
            index: 3,
            total: 4,
            name: "Checking baseline",
            label: "正在检查 baseline 可用性。"
          }
        }
      ]);
    }

    void this.executeIssueJob(job, { casePath: options.casePath, live: options.live }, resultFilePath);
    return this.snapshot(job);
  }

  private async scanFlowProgress(job: MutableJob, flow: string, jobStartedAt: number): Promise<void> {
    try {
      const resultBase = resolveRepoPath("json/flow_results");
      const entries = await fs.readdir(resultBase);
      const flowDirs = entries
        .filter((name) => name.startsWith(`${flow}_`))
        .sort()
        .reverse();

      let foundRunId: string | undefined;
      for (const dir of flowDirs) {
        const dirPath = resolveRepoPath(path.join("json/flow_results", dir));
        try {
          const stat = await fs.stat(dirPath);
          if (stat.birthtimeMs >= jobStartedAt - 2000 || stat.mtimeMs >= jobStartedAt - 2000) {
            foundRunId = dir;
            break;
          }
        } catch {
          continue;
        }
      }

      const prev = (job.resultSummary ?? {}) as Record<string, unknown>;
      const next = { ...prev };

      if (foundRunId && !prev.liveRunId) {
        next.liveRunId = foundRunId;
        this.note(job, `检测到 Run: ${foundRunId}`);
      }

      if (foundRunId) {
        const resultPath = resolveRepoPath(path.join("json/flow_results", foundRunId, "result.json"));
        const data = await this.safeReadJson(resultPath);
        if (data) {
          if (Array.isArray(data.checks)) {
            next.liveChecks = data.checks;
          }
          if (data.counts) {
            next.liveCounts = data.counts;
          }
          if (Array.isArray(data.timeline)) {
            next.liveTimeline = data.timeline;
          }
          next.result = data.result;
          job.resultPath = resultPath;
        }
      }

      job.resultSummary = next;
    } catch {
      // scan failed, ignore
    }
  }

  private async executeFlowJob(
    job: MutableJob,
    flow: string
  ): Promise<void> {
    const command = `bash scripts/flows/run_ue_flow.sh ${flow}`;
    const jobStartedAt = new Date(job.startedAt).getTime();

    const scanTimer = setInterval(() => {
      if (job.settled || job.aborted) {
        clearInterval(scanTimer);
        return;
      }
      void this.scanFlowProgress(job, flow, jobStartedAt);
    }, 3000);
    job.timers.push(scanTimer as unknown as NodeJS.Timeout);

    try {
      const exitCode = await this.startProcess(job, command);
      if (job.aborted || job.settled) {
        return;
      }

      clearInterval(scanTimer);

      this.markStage(job, {
        index: job.stepTotal,
        total: job.stepTotal,
        name: "Collecting result",
        label: "正在读取 flow 结果文件。",
        status: "collecting_results"
      });
      this.note(job, "正在读取 flow 结果文件");

      await this.scanFlowProgress(job, flow, jobStartedAt);

      const resultSummary = job.resultSummary;
      const resultValue = typeof resultSummary?.result === "string" ? String(resultSummary.result) : "";
      const acceptedResult = exitCode === 0 && resultValue === "PASS";

      if (!acceptedResult && !job.error) {
        job.error = `unexpected result: exit=${exitCode}, result=${resultValue || "unknown"}`;
      }

      this.finalizeJob(job, acceptedResult ? "completed" : "completed_with_failure");
    } catch (error) {
      if (job.aborted || job.settled) {
        return;
      }
      job.error = error instanceof Error ? error.message : "flow job failed";
      this.finalizeJob(job, "completed_with_failure");
    }
  }

  async startFlowJob(flow: string): Promise<JobSummary> {
    this.ensureMutatingCapacity();

    const label = flow === "registration_release" ? "Registration + Release" : "Registration + PDU Session";
    const job = this.register(newJob("ue_flow", `UE Flow: ${label}`, true));
    this.currentMutatingJobId = job.id;

    this.markStage(job, {
      index: 1,
      total: 4,
      name: "Checking baseline",
      label: "正在确认 baseline 健康。",
      status: "running"
    });
    this.scheduleStages(job, [
      {
        afterMs: 2000,
        stage: {
          index: 2,
          total: 4,
          name: "Running UE flow",
          label: `正在执行 ${label}，请等待完成。`
        }
      },
      {
        afterMs: 15000,
        stage: {
          index: 3,
          total: 4,
          name: "Collecting results",
          label: "正在收集抓包和日志结果。"
        }
      }
    ]);

    void this.executeFlowJob(job, flow);
    return this.snapshot(job);
  }
}
