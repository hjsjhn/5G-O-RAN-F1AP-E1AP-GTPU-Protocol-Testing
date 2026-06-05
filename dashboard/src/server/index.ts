import express from "express";
import path from "node:path";
import {
  getIssueCases,
  getLatestFlows,
  getProtocolReplayCards,
  getReports,
  getSystemStatus,
  readMarkdownBySlug,
  readWhitelistedFile,
  repoRoot
} from "./data.js";
import { JobManager } from "./jobs.js";

const app = express();
const jobManager = new JobManager();
const port = Number(process.env.DASHBOARD_PORT ?? 4174);

app.use(express.json({ limit: "1mb" }));

app.get("/api/status/system", async (_request, response) => {
  response.json(await getSystemStatus(jobManager.getLastRestoreState(), jobManager.getCurrentMutatingJob()));
});

app.post("/api/system/restore", async (_request, response) => {
  try {
    const job = await jobManager.startRestoreJob();
    response.status(202).json(job);
  } catch (error) {
    response.status(409).json({ error: error instanceof Error ? error.message : "restore failed" });
  }
});

app.get("/api/issues", async (_request, response) => {
  response.json(await getIssueCases());
});

app.post("/api/issues/:id/dry-run", async (request, response) => {
  const cases = await getIssueCases();
  const current = cases.find((item) => item.id === request.params.id);
  if (!current) {
    response.status(404).json({ error: "case not found" });
    return;
  }
  try {
    const job = await jobManager.startIssueJob({
      caseId: current.id,
      casePath: current.casePath,
      live: false
    });
    response.status(202).json(job);
  } catch (error) {
    response.status(409).json({ error: error instanceof Error ? error.message : "dry-run failed" });
  }
});

app.post("/api/issues/:id/live-run", async (request, response) => {
  const confirmed = request.body?.confirmed === true;
  if (!confirmed) {
    response.status(400).json({
      error: "需要确认此操作可能故意打崩 Open5GS NF，随后会自动恢复 baseline。"
    });
    return;
  }
  const cases = await getIssueCases();
  const current = cases.find((item) => item.id === request.params.id);
  if (!current) {
    response.status(404).json({ error: "case not found" });
    return;
  }
  try {
    const job = await jobManager.startIssueJob({
      caseId: current.id,
      casePath: current.casePath,
      live: true
    });
    response.status(202).json(job);
  } catch (error) {
    response.status(409).json({ error: error instanceof Error ? error.message : "live run failed" });
  }
});

app.get("/api/jobs", (_request, response) => {
  response.json(jobManager.listJobs());
});

app.get("/api/jobs/:id", (request, response) => {
  const job = jobManager.getJob(request.params.id);
  if (!job) {
    response.status(404).json({ error: "job not found" });
    return;
  }
  response.json(job);
});

app.post("/api/jobs/:id/abort-and-restore", async (request, response) => {
  try {
    const job = await jobManager.abortAndRestore(request.params.id);
    response.json(job);
  } catch (error) {
    response.status(409).json({ error: error instanceof Error ? error.message : "abort failed" });
  }
});

app.get("/api/flows/latest", async (_request, response) => {
  response.json(await getLatestFlows());
});

app.get("/api/protocol-replay", (_request, response) => {
  response.json(getProtocolReplayCards());
});

app.get("/api/reports", async (_request, response) => {
  response.json(await getReports());
});

app.get("/api/reports/:slug", async (request, response) => {
  const document = await readMarkdownBySlug(request.params.slug);
  if (!document) {
    response.status(404).json({ error: "report not found" });
    return;
  }
  response.json(document);
});

app.get("/api/file", async (request, response) => {
  const targetPath = String(request.query.path ?? "");
  if (!targetPath) {
    response.status(400).json({ error: "missing path" });
    return;
  }
  const document = await readWhitelistedFile(targetPath);
  if (!document) {
    response.status(403).json({ error: "path is not whitelisted" });
    return;
  }
  response.json(document);
});

const clientDist = path.resolve(repoRoot, "dashboard/dist/client");
app.use(express.static(clientDist));
app.get("*", (_request, response) => {
  response.sendFile(path.resolve(clientDist, "index.html"));
});

app.listen(port, () => {
  console.log(`Dashboard API listening on http://127.0.0.1:${port}`);
});
