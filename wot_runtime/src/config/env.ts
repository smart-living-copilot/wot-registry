function parseIntEnv(name: string, fallback: number): number {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const parsed = Number.parseInt(rawValue, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseNonNegativeIntEnv(name: string, fallback: number): number {
  return Math.max(0, parseIntEnv(name, fallback));
}

function requiredStringEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (value) {
    return value;
  }

  throw new Error(`Missing required environment variable: ${name}`);
}

export const config = {
  host: process.env.HOST || '127.0.0.1',
  port: parseIntEnv('PORT', 3003),
  registryUrl: process.env.REGISTRY_URL || 'http://localhost:8000',
  registryServiceName: process.env.REGISTRY_SERVICE_NAME || 'wot_runtime',
  registryServiceToken: requiredStringEnv('WOT_RUNTIME_REGISTRY_TOKEN'),
  runtimeApiToken: requiredStringEnv('WOT_RUNTIME_API_TOKEN'),
  secretsPath: process.env.SECRETS_PATH || './secrets.json',
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  streamName: process.env.WOT_RUNTIME_STREAM || 'wot_runtime_events',
  requestTimeoutMs: parseIntEnv('HTTP_REQUEST_TIMEOUT_MS', 10000),
  subscriptionSetupTimeoutMs: parseIntEnv('WOT_SUBSCRIPTION_SETUP_TIMEOUT_MS', 0),
  secretsRefreshIntervalMs: parseIntEnv('SECRETS_REFRESH_INTERVAL_MS', 60000),
  inlinePayloadMaxBytes: parseNonNegativeIntEnv('WOT_INLINE_PAYLOAD_MAX_BYTES', 65536),
  offloadedPayloadTtlSeconds: parseNonNegativeIntEnv('WOT_OFFLOADED_PAYLOAD_TTL_SECONDS', 86400),
} as const;

export type AppConfig = typeof config;
