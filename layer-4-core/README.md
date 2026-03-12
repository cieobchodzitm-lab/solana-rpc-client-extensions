# Layer 4 Core — Cognitive Security Engine

**Angel Guardian Technologies**

Layer 4 Core is an AI-powered cognitive security engine that analyzes digital communications for psychological manipulation patterns. It combines Dark Triad detection with Stoic philosophy to help users identify harmful communication and respond from wisdom rather than impulse.

## Features

- **Dark Triad Detection** — Identifies narcissism, Machiavellianism, and psychopathy patterns
- **Threat Scoring** — 0–100 scale with five severity levels
- **Pattern Recognition** — Detects 14+ distinct manipulation tactics
- **Stoic Shield** — Philosophical guidance grounded in Marcus Aurelius, Epictetus, and Seneca
- **Actionable Recommendations** — Concrete tactical advice for each situation
- **Safety Override** — Immediate escalation for physical danger or self-harm indicators

## Setup

```bash
npm install
export ANTHROPIC_API_KEY="your-api-key"
```

## Usage

### CLI

```bash
# Analyze a message passed as an argument
npm run analyze "After everything I've done for you, this is how you repay me?"

# Pipe from stdin
echo "I need an answer RIGHT NOW, I cannot wait any longer." | npm run analyze
```

### Programmatic

```typescript
import { analyzeMessage } from "./src/analyze.js";

const result = await analyzeMessage("Your message here");
if (typeof result !== "string") {
  console.log(result.threat_score);     // 0–100
  console.log(result.primary_intent);  // e.g., "Emotional Blackmail"
  console.log(result.detected_patterns); // ["Guilt-Tripping", "Victim Playing"]
  console.log(result.stoic_nudge);     // Philosophical guidance
  console.log(result.suggested_action); // Tactical recommendation
}
```

### Output JSON mode

Set `OUTPUT_JSON=1` to also print the raw JSON result:

```bash
OUTPUT_JSON=1 npm run analyze "Your message here"
```

## Threat Score Reference

| Score | Level    | Meaning                                          |
|-------|----------|--------------------------------------------------|
| 0–20  | MINIMAL  | Healthy communication, no intervention needed   |
| 21–40 | LOW      | Minor patterns, situational awareness advised    |
| 41–60 | MODERATE | Clear manipulation; proceed with caution         |
| 61–80 | HIGH     | Significant harm potential; strong boundaries    |
| 81–100| CRITICAL | Severe manipulation; consider exiting dynamic    |

## Architecture

- **`src/system-prompt.ts`** — The detailed Layer 4 Core system prompt
- **`src/analyze.ts`** — Core analysis engine using Claude Opus 4.6 with adaptive thinking
- **`src/types.ts`** — TypeScript interfaces for analysis results
- **`src/index.ts`** — CLI entry point with formatted output

## Model

Uses **Claude Opus 4.6** with adaptive thinking (`thinking: { type: "adaptive" }`) for maximum analytical depth on complex manipulation patterns.
