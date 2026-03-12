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

  const stream = client.messages.stream({
    model: "claude-opus-4-6",
    max_tokens: 2048,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    thinking: { type: "adaptive" } as any,
    system: SYSTEM_PROMPT,
    messages: [
      {
        role: "user",
        content: `Analyze the following message for psychological manipulation patterns:\n\n"""\n${message}\n"""`,
      },
    ],
  });

  const finalMessage = await stream.finalMessage();

  const textBlock = finalMessage.content.find((block) => block.type === "text");
  if (!textBlock || textBlock.type !== "text") {
    throw new Error("No text response received from Claude");
  }

  let jsonText = textBlock.text.trim();

  // Strip markdown code fences if present (defensive handling)
  const fenceMatch = jsonText.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (fenceMatch) {
    jsonText = fenceMatch[1];
  }

  try {
    const result = JSON.parse(jsonText) as AnalysisResult;
    return result;
  } catch {
    throw new Error(`Failed to parse response as JSON: ${jsonText}`);
  }
}
