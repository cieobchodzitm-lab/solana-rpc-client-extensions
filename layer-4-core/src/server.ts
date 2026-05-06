import express, { Request, Response, NextFunction } from "express";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";
import { analyzeMessage } from "./analyze.js";
import type { AnalysisResult } from "./types.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
const PORT = process.env["PORT"] ? parseInt(process.env["PORT"]) : 3000;

// ── API key auth ───────────────────────────────────────────────
// If LAYER4_API_KEY is set, every request to /analyze must supply it
// via the X-API-Key header. The web UI and /health are always public.
const LAYER4_API_KEY = process.env["LAYER4_API_KEY"]?.trim() || null;

function requireApiKey(req: Request, res: Response, next: NextFunction): void {
  if (!LAYER4_API_KEY) {
    // No key configured → auth disabled (development mode)
    next();
    return;
  }

  const provided = req.headers["x-api-key"];
  if (typeof provided !== "string" || provided !== LAYER4_API_KEY) {
    res.status(401).json({ error: "Missing or invalid X-API-Key header." });
    return;
  }

  next();
}

app.use(cors());
app.use(express.json({ limit: "64kb" }));

// Serve the web UI from /public (always public — no auth required)
const publicDir = path.join(__dirname, "..", "public");
app.use(express.static(publicDir));

// ── Health check (public) ──────────────────────────────────────
app.get("/health", (_req: Request, res: Response) => {
  res.json({
    status: "ok",
    service: "layer-4-core",
    auth: LAYER4_API_KEY ? "enabled" : "disabled",
  });
});

// ── POST /analyze (protected) ──────────────────────────────────
// Headers: X-API-Key: <LAYER4_API_KEY>   (required when auth is enabled)
// Body:    { "message": "<text to analyze>" }
// 200:     AnalysisResult JSON
// 200:     { "safety_alert": true, "message": "..." }  — crisis override
// 400:     { "error": "..." }  — bad request
// 401:     { "error": "..." }  — missing/wrong API key
// 500:     { "error": "..." }  — internal error
app.post(
  "/analyze",
  requireApiKey,
  async (req: Request, res: Response, next: NextFunction) => {
    const { message } = req.body as { message?: unknown };

    if (typeof message !== "string" || !message.trim()) {
      res
        .status(400)
        .json({ error: "Body must contain a non-empty 'message' string." });
      return;
    }

    try {
      const result = await analyzeMessage(message.trim());

      if (typeof result === "string") {
        res.status(200).json({ safety_alert: true, message: result });
        return;
      }

      res.json(result satisfies AnalysisResult);
    } catch (err) {
      next(err);
    }
  },
);

// ── Error handler ──────────────────────────────────────────────
// Log the full error server-side but never reflect raw error messages back
// to the client — they may contain upstream API text, partial keys, or LLM output.
app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
  console.error("[layer-4-core]", err);
  res.status(500).json({ error: "Internal server error" });
});

app.listen(PORT, () => {
  console.log(`Layer 4 Core API  →  http://localhost:${PORT}`);
  console.log(`  GET  /health`);
  console.log(`  POST /analyze   (auth: ${LAYER4_API_KEY ? "X-API-Key required" : "disabled — set LAYER4_API_KEY to enable"})`);
});

export { app };
