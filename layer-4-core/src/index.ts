#!/usr/bin/env node
import { analyzeMessage } from "./analyze.js";
import type { AnalysisResult } from "./types.js";

function printResult(result: AnalysisResult | string): void {
  if (typeof result === "string") {
    // Physical safety override — plain text response
    console.error("\n⚠️  SAFETY ALERT\n");
    console.error(result);
    process.exit(1);
  }

  const threatLabel =
    result.threat_score <= 20
      ? "MINIMAL"
      : result.threat_score <= 40
        ? "LOW"
        : result.threat_score <= 60
          ? "MODERATE"
          : result.threat_score <= 80
            ? "HIGH"
            : "CRITICAL";

  console.log("\n" + "═".repeat(60));
  console.log(`  LAYER 4 CORE — COGNITIVE SECURITY ANALYSIS`);
  console.log("═".repeat(60));
  console.log(
    `  Threat Score : ${result.threat_score}/100 [${threatLabel}]`,
  );
  console.log(`  Primary Intent: ${result.primary_intent}`);
  console.log("─".repeat(60));

  if (result.detected_patterns.length > 0) {
    console.log("\n  DETECTED PATTERNS:");
    for (const pattern of result.detected_patterns) {
      console.log(`    • ${pattern}`);
    }
  } else {
    console.log("\n  DETECTED PATTERNS: None — healthy communication");
  }

  console.log("\n  ANALYSIS:");
  console.log(wordWrap(result.analysis_summary, 56, "  "));

  console.log("\n  STOIC SHIELD:");
  console.log(wordWrap(result.stoic_nudge, 56, "  "));

  console.log("\n  RECOMMENDED ACTION:");
  console.log(wordWrap(result.suggested_action, 56, "  "));

  if (result.code_execution_steps && result.code_execution_steps.length > 0) {
    console.log("\n  CODE EXECUTION STEPS:");
    for (const [i, step] of result.code_execution_steps.entries()) {
      console.log(`\n  ── Step ${i + 1} [${step.type}] ──`);
      if (step.type === "bash") {
        if (step.error_code) {
          console.log(`  ERROR: ${step.error_code}`);
        } else {
          console.log(`  exit: ${step.return_code}`);
          if (step.stdout) console.log("  stdout:\n  " + step.stdout.split("\n").join("\n  "));
          if (step.stderr) console.log("  stderr:\n  " + step.stderr.split("\n").join("\n  "));
          if (step.output_file_ids?.length)
            console.log("  files:", step.output_file_ids.join(", "));
        }
      } else {
        console.log(`  operation: ${step.operation}`);
        if (step.error_code)   console.log(`  error: ${step.error_code}`);
        if (step.file_content) console.log("  content:\n  " + step.file_content.slice(0, 200));
      }
    }
  }

  console.log("\n" + "═".repeat(60) + "\n");

  // Also output raw JSON for programmatic consumers
  if (process.env["OUTPUT_JSON"] === "1") {
    console.log(JSON.stringify(result, null, 2));
  }
}

function wordWrap(text: string, width: number, indent: string): string {
  const words = text.split(" ");
  const lines: string[] = [];
  let currentLine = "";

  for (const word of words) {
    if (currentLine.length + word.length + 1 <= width) {
      currentLine += (currentLine ? " " : "") + word;
    } else {
      if (currentLine) lines.push(indent + currentLine);
      currentLine = word;
    }
  }
  if (currentLine) lines.push(indent + currentLine);

  return lines.join("\n");
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk as string));
  }
  return Buffer.concat(chunks).toString("utf8").trim();
}

async function main(): Promise<void> {
  let message: string;

  // Accept message from CLI args or stdin
  const args = process.argv.slice(2);

  if (args.length > 0) {
    message = args.join(" ");
  } else if (!process.stdin.isTTY) {
    message = await readStdin();
  } else {
    console.error(
      "Usage: node dist/index.js <message>\n       echo '<message>' | node dist/index.js",
    );
    console.error(
      "\nExample: node dist/index.js \"After everything I've done for you, this is how you repay me?\"",
    );
    process.exit(1);
  }

  if (!message) {
    console.error("Error: No message provided for analysis.");
    process.exit(1);
  }

  console.log("\nAnalyzing message...");

  try {
    const result = await analyzeMessage(message);
    printResult(result);
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    console.error(`\nAnalysis failed: ${msg}`);
    process.exit(1);
  }
}

main();
