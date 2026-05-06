import Anthropic from "@anthropic-ai/sdk";
import { SYSTEM_PROMPT } from "./system-prompt.js";
import type { AnalysisResult, CodeExecutionStep } from "./types.js";

const client = new Anthropic();

const PHYSICAL_SAFETY_KEYWORDS = [
  "i'm going to hurt you",
  "i am going to hurt you",
  "i know where you live",
  "i'm going to kill",
  "i am going to kill",
  "kill myself",
  "end my life",
  "suicide",
];

function checkPhysicalSafety(message: string): boolean {
  const lowerMessage = message.toLowerCase();
  return PHYSICAL_SAFETY_KEYWORDS.some((keyword) =>
    lowerMessage.includes(keyword),
  );
}

// Latest code execution tool — supports REPL state persistence via gVisor checkpoint.
const CODE_EXECUTION_TOOL: Anthropic.Messages.CodeExecutionTool20260120 = {
  type: "code_execution_20260120",
  name: "code_execution",
};

// Maximum number of pause_turn continuations before giving up.
const MAX_CONTINUATIONS = 5;

// Set DEBUG_BLOCKS=1 to log raw content block shapes for every API response.
const DEBUG = process.env["DEBUG_BLOCKS"] === "1";

function debugLog(label: string, data: unknown): void {
  if (DEBUG) {
    console.error(`\n[Layer4 DEBUG] ${label}:`);
    console.error(JSON.stringify(data, null, 2));
  }
}

/** Process a single bash_code_execution_tool_result block into a CodeExecutionStep. */
function processBashResult(
  block: Anthropic.Messages.BashCodeExecutionToolResultBlock,
): CodeExecutionStep {
  debugLog("bash_code_execution_tool_result", block);

  const content = block.content;

  if (content.type === "bash_code_execution_tool_result_error") {
    return {
      type: "bash",
      error_code: content.error_code,
      stdout: "",
      stderr: "",
      return_code: -1,
    };
  }

  // content.type === "bash_code_execution_result"
  return {
    type: "bash",
    stdout: content.stdout,
    stderr: content.stderr,
    return_code: content.return_code,
    output_file_ids: content.content
      .filter(
        (o): o is Anthropic.Messages.BashCodeExecutionOutputBlock =>
          o.type === "bash_code_execution_output",
      )
      .map((o) => o.file_id),
  };
}

/** Process a text_editor_code_execution_tool_result block into a CodeExecutionStep. */
function processEditorResult(
  block: Anthropic.Messages.TextEditorCodeExecutionToolResultBlock,
): CodeExecutionStep {
  debugLog("text_editor_code_execution_tool_result", block);

  const content = block.content;

  if (content.type === "text_editor_code_execution_tool_result_error") {
    return {
      type: "editor",
      error_code: content.error_code,
      operation: "error",
    };
  }

  switch (content.type) {
    case "text_editor_code_execution_view_result":
      return {
        type: "editor",
        operation: "view",
        file_content: content.content,   // SDK field name is `content`, not `file_text`
        file_type: content.file_type,
      };
    case "text_editor_code_execution_create_result":
      return { type: "editor", operation: "create" };
    case "text_editor_code_execution_str_replace_result":
      return {
        type: "editor",
        operation: "str_replace",
        old_start: content.old_start ?? undefined, // line numbers
        new_start: content.new_start ?? undefined,
      };
    default:
      return { type: "editor", operation: "unknown" };
  }
}

export async function analyzeMessage(
  message: string,
): Promise<AnalysisResult | string> {
  if (checkPhysicalSafety(message)) {
    return (
      "SAFETY ALERT: This message contains content suggesting immediate physical danger or self-harm. " +
      "Please contact emergency services immediately (911 in the US, 999 in the UK, 112 in Europe) " +
      "or a crisis hotline such as the National Suicide Prevention Lifeline at 988 (US) or " +
      "Crisis Text Line by texting HOME to 741741 (US). Your safety is the highest priority."
    );
  }

  const userContent =
    `Analyze the following message for psychological manipulation patterns. ` +
    `You may use code execution to perform linguistic analysis (e.g. pronoun counting, ` +
    `urgency-word detection, sentiment scoring) to support your evaluation.\n\n` +
    `"""\n${message}\n"""`;

  let messages: Anthropic.MessageParam[] = [
    { role: "user", content: userContent },
  ];

  const steps: CodeExecutionStep[] = [];
  let finalJsonText: string | null = null;

  // System prompt with prompt caching — the large, stable prefix is cached
  // across requests, cutting input token cost on cache hits.
  const cachedSystem: Anthropic.Messages.TextBlockParam[] = [
    {
      type: "text",
      text: SYSTEM_PROMPT,
      cache_control: { type: "ephemeral" },
    },
  ];

  for (let attempt = 0; attempt < MAX_CONTINUATIONS; attempt++) {
    const stream = client.messages.stream({
      model: "claude-opus-4-7",
      max_tokens: 8192,
      thinking: { type: "adaptive" },
      tools: [CODE_EXECUTION_TOOL],
      system: cachedSystem,
      messages,
    });

    const response = await stream.finalMessage();

    // Log cache hit/miss stats so operators can verify caching is working.
    const u = response.usage as unknown as Record<string, number>;
    debugLog(
      `response turn ${attempt + 1} — stop_reason=${response.stop_reason} | usage`,
      {
        input_tokens: u["input_tokens"],
        cache_creation_input_tokens: u["cache_creation_input_tokens"] ?? 0,
        cache_read_input_tokens: u["cache_read_input_tokens"] ?? 0,
        output_tokens: u["output_tokens"],
      },
    );
    debugLog(`response turn ${attempt + 1} — block types`, {
      block_types: response.content.map((b) => b.type),
    });

    // ── Collect code execution results ───────────────────────────────────
    for (const block of response.content) {
      if (block.type === "bash_code_execution_tool_result") {
        steps.push(processBashResult(block));
      } else if (block.type === "text_editor_code_execution_tool_result") {
        steps.push(processEditorResult(block));
      }
    }

    // ── Handle stop reason ───────────────────────────────────────────────
    if (response.stop_reason === "end_turn") {
      // Find the LAST text block — it contains the final JSON output.
      // Earlier text blocks may be Claude's reasoning before running code.
      const textBlocks = response.content.filter(
        (b): b is Anthropic.TextBlock => b.type === "text",
      );

      if (textBlocks.length === 0) {
        throw new Error(
          "No text block in final response. Block types received: " +
          response.content.map((b) => b.type).join(", "),
        );
      }

      finalJsonText = textBlocks[textBlocks.length - 1].text.trim();
      break;
    }

    if (response.stop_reason === "pause_turn") {
      // Server-side tool loop hit its 10-iteration limit.
      // Re-send original user message + assistant content to continue.
      messages = [
        { role: "user", content: userContent },
        { role: "assistant", content: response.content },
      ];
      continue;
    }

    throw new Error(`Unexpected stop_reason: "${response.stop_reason}"`);
  }

  if (!finalJsonText) {
    throw new Error(
      `Analysis did not complete after ${MAX_CONTINUATIONS} continuations.`,
    );
  }

  // Strip markdown code fences if present (defensive handling).
  const fenceMatch = finalJsonText.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (fenceMatch) {
    finalJsonText = fenceMatch[1];
  }

  debugLog("final JSON text", finalJsonText);

  try {
    const result = JSON.parse(finalJsonText) as AnalysisResult;
    if (steps.length > 0) {
      result.code_execution_steps = steps;
    }
    return result;
  } catch {
    throw new Error(`Failed to parse response as JSON:\n${finalJsonText}`);
  }
}
