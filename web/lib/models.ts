export type ModelProvider = "kimi" | "deepseek" | "mimo";

interface ProviderConfig {
  base: string;
  envKey: string;
  model: string;
}

const PROVIDERS: Record<ModelProvider, ProviderConfig> = {
  kimi: {
    base: "https://api.moonshot.ai/anthropic",
    envKey: "KIMI_ANTHROPIC_API_KEY",
    model: "kimi-k2.7-code",
  },
  deepseek: {
    base: "https://api.deepseek.com/anthropic",
    envKey: "DEEPSEEK_ANTHROPIC_API_KEY",
    model: "deepseek-v4-pro",
  },
  mimo: {
    base: "https://token-plan-sgp.xiaomimimo.com/anthropic",
    envKey: "MIMO_API_KEY",
    model: "mimo-v2.5",
  },
};

interface AnthropicContentBlock {
  type: string;
  text?: string;
}

interface AnthropicMessagesResponse {
  content: AnthropicContentBlock[];
}

const REQUEST_TIMEOUT_MS = 120_000;

/**
 * Calls an Anthropic-compatible messages endpoint for the given provider.
 * Forces a bounded thinking budget to avoid burning the full token allocation.
 */
export async function askModel(
  provider: ModelProvider,
  prompt: string,
  opts: { maxTokens?: number; system?: string } = {},
): Promise<string> {
  const config = PROVIDERS[provider];
  const key = process.env[config.envKey];

  if (!key) {
    throw new Error(`${config.envKey} is not configured`);
  }

  // The model requires max_tokens to exceed the thinking budget.
  const maxTokens = Math.max(opts.maxTokens ?? 4000, 8000);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${config.base}/v1/messages`, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "x-api-key": key,
        authorization: `Bearer ${key}`,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: config.model,
        max_tokens: maxTokens,
        thinking: { type: "enabled", budget_tokens: 6000 },
        messages: [{ role: "user", content: prompt }],
        ...(opts.system ? { system: opts.system } : {}),
      }),
    });

    if (!response.ok) {
      const bodyText = await response.text();
      throw new Error(
        `${provider} model failed (${response.status}): ${bodyText.slice(0, 300)}`,
      );
    }

    const data = (await response.json()) as AnthropicMessagesResponse;

    return (data.content ?? [])
      .filter(
        (block): block is AnthropicContentBlock & { type: "text"; text: string } =>
          block.type === "text" && typeof block.text === "string",
      )
      .map((block) => block.text)
      .join("");
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Finds the first {...} JSON object in a free-text response and parses it.
 * Returns null if no valid object is found.
 */
export function extractJson(text: string): unknown | null {
  const start = text.indexOf("{");
  if (start === -1) return null;

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < text.length; i++) {
    const char = text[i];
    // Ignore braces that appear inside JSON string values (and handle escapes).
    if (inString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') {
      inString = true;
    } else if (char === "{") {
      depth++;
    } else if (char === "}") {
      depth--;
      if (depth === 0) {
        try {
          return JSON.parse(text.slice(start, i + 1));
        } catch {
          return null;
        }
      }
    }
  }

  return null;
}
