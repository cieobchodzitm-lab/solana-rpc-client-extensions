import Anthropic from "@anthropic-ai/sdk";
import { SYSTEM_PROMPT } from "./system-prompt.js";
import type { AnalysisResult } from "./types.js";

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

// Latest code execution tool — supports REPL state persistence (gVisor checkpoint).
// Cast to any because SDK 0.52.0 types predate the _20260120 version string.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CODE_EXECUTION_TOOL: any = {
  type: "code_execution_20260120",
  name: "code_execution",
};

// Maximum number of pause_turn continuations before giving up.
const MAX_CONTINUATIONS = 5;

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

  // Messages array grows when pause_turn continuations are needed.
  let messages: Anthropic.MessageParam[] = [
    { role: "user", content: userContent },
  ];

  const codeExecutionOutputs: string[] = [];
  let finalJsonText: string | null = null;

  for (let attempt = 0; attempt < MAX_CONTINUATIONS; attempt++) {
    const stream = client.messages.stream({
      model: "claude-opus-4-6",
      max_tokens: 8192,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      thinking: { type: "adaptive" } as any,
      tools: [CODE_EXECUTION_TOOL],
      system: SYSTEM_PROMPT,
      messages,
    });

    const response = await stream.finalMessage();

    // Collect stdout from bash_code_execution_tool_result blocks.
    // The type string is not in SDK 0.52.0's union so we cast via unknown.
    for (const block of response.content as unknown[]) {
      const b = block as { type: string; content?: { stdout?: string } };
      if (
        b.type === "bash_code_execution_tool_result" &&
        b.content?.stdout?.trim()
      ) {
        codeExecutionOutputs.push(b.content.stdout.trim());
      }
    }

    if (response.stop_reason === "end_turn") {
      // Find the LAST text block — it contains the final JSON output.
      // (Earlier text blocks may be Claude's reasoning before running code.)
      const textBlocks = response.content.filter(
        (b): b is Anthropic.TextBlock => b.type === "text",
      );

      if (textBlocks.length === 0) {
        throw new Error(
          "No text response received from Claude. " +
          "Response contained: " +
          response.content.map((b) => b.type).join(", "),
        );
      }

      finalJsonText = textBlocks[textBlocks.length - 1].text.trim();
      break;
    }

    if (response.stop_reason === "pause_turn") {
      // Server-side tool loop hit its iteration limit — re-send to continue.
      // Per API docs: append assistant content and re-send the original user message.
      messages = [
        { role: "user", content: userContent },
        { role: "assistant", content: response.content },
      ];
      continue;
    }

    throw new Error(`Unexpected stop_reason: ${response.stop_reason}`);
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

  try {
    const result = JSON.parse(finalJsonText) as AnalysisResult;
    if (codeExecutionOutputs.length > 0) {
      result.code_execution_output = codeExecutionOutputs;
    }
    return result;
  } catch {
    throw new Error(`Failed to parse response as JSON:\n${finalJsonText}`);
  }
}
