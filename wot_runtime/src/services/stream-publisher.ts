import { Redis as RedisClient } from 'ioredis';

import { config } from '../config/env.js';
import log from '../logger/index.js';
import { formatError } from './errors.js';

type RuntimeStreamEvent = {
  eventType: string;
  thingId: string;
  interactionType: 'property' | 'event';
  name: string;
  subscriptionId: string;
  deliveryId?: string;
  payloadBase64?: string;
  contentType?: string;
  timestamp?: string;
  sourceProtocol?: string;
  requiresResponse?: boolean;
  detail?: string;
};

let redisPromise: Promise<RedisClient> | null = null;

async function createRedisClient(): Promise<RedisClient> {
  const client = new RedisClient(config.redisUrl, {
    lazyConnect: true,
    maxRetriesPerRequest: 1,
  });

  client.on('error', (error: unknown) => {
    log.error(`Valkey error: ${formatError(error)}`);
  });

  await client.connect();
  return client;
}

async function getRedisClient(): Promise<RedisClient> {
  if (!redisPromise) {
    redisPromise = createRedisClient().catch((error) => {
      redisPromise = null;
      throw error;
    });
  }

  return redisPromise;
}

function toFieldValue(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }

  return String(value);
}

export async function publishRuntimeStreamEvent(
  event: RuntimeStreamEvent
): Promise<void> {
  const client = await getRedisClient();
  const fields = [
    'event_type',
    event.eventType,
    'thing_id',
    event.thingId,
    'interaction_type',
    event.interactionType,
    'name',
    event.name,
    'subscription_id',
    event.subscriptionId,
    'delivery_id',
    toFieldValue(event.deliveryId),
    'payload_base64',
    toFieldValue(event.payloadBase64),
    'content_type',
    toFieldValue(event.contentType),
    'timestamp',
    event.timestamp || new Date().toISOString(),
    'source_protocol',
    toFieldValue(event.sourceProtocol),
    'requires_response',
    toFieldValue(event.requiresResponse || false),
    'detail',
    toFieldValue(event.detail),
  ] as const;

  await client.xadd(config.streamName, '*', ...fields);
}

export async function pingValkey(): Promise<boolean> {
  try {
    const client = await getRedisClient();
    return (await client.ping()) === 'PONG';
  } catch {
    return false;
  }
}

export async function closeValkeyClient(): Promise<void> {
  if (!redisPromise) {
    return;
  }

  const client = await redisPromise.catch(() => null);
  redisPromise = null;
  await client?.quit().catch(() => undefined);
}
