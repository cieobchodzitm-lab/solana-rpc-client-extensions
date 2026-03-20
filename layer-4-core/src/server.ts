import express, { Request, Response, NextFunction } from "express";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";
import { analyzeMessage } from "./analyze.js";
import type { AnalysisResult } from "./types.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
const PORT = process.env["PORT"] ? parseInt(process.env["PORT"]) : 3000;

app.use(cors());
app.use(express.json());

// Serve the web UI from /public
const publicDir = path.join(__dirname, "..", "public");
app.use(express.static(publicDir));

// ── Health check ──────────────────────────────────────────────
app.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok", service: "layer-4-core" });
});

// ── POST /analyze ──────────────────────────────────────────────
// Body: { "message": "<text to analyze>" }
// Response 200: AnalysisResult JSON
// Response 200: { "safety_alert": true, "message": "<plain text>" }  — crisis override
// Response 400: { "error": "<description>" }
// Response 500: { "error": "<description>" }
app.post(
  "/analyze",
  async (req: Request, res: Response, next: NextFunction) => {
    const { message } = req.body as { message?: unknown };

    if (typeof message !== "string" || !message.trim()) {
      res.status(400).json({ error: "Body must contain a non-empty 'message' string." });
      return;
    }

    try {
      const result = await analyzeMessage(message.trim());

      if (typeof result === "string") {
        // Physical safety override
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
app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
  const message = err instanceof Error ? err.message : "Internal server error";
  console.error("[layer-4-core]", err);
  res.status(500).json({ error: message });
});

app.listen(PORT, () => {
  console.log(`Layer 4 Core API running on http://localhost:${PORT}`);
  console.log(`  POST /analyze   { "message": "..." }`);
  console.log(`  GET  /health`);
});

export { app };
