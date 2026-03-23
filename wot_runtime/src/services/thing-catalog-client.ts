import crypto from 'node:crypto';

import axios, { AxiosError } from 'axios';

import { config } from '../config/env.js';

export type ThingDescription = Record<string, unknown>;

function thingsUrl(path: string): string {
  const trimmed = path.replace(/^\/+/, '');
  if (!trimmed) {
    return `${config.registryUrl}/api/things`;
  }
  return `${config.registryUrl}/api/things/${trimmed}`;
}

export function registryServiceHeaders(): Record<string, string> | undefined {
  if (!config.registryServiceToken) {
    return undefined;
  }

  return {
    'X-Registry-Service': config.registryServiceName,
    'X-Registry-Service-Token': config.registryServiceToken,
  };
}

function extractThingDocument(payload: ThingDescription): ThingDescription {
  const embedded = payload.document;
  if (embedded && typeof embedded === 'object' && !Array.isArray(embedded)) {
    return embedded as ThingDescription;
  }
  return payload;
}

export function extractRegistryErrorMessage(
  error: unknown,
  fallback: string
): string {
  if (error instanceof AxiosError) {
    const payload = error.response?.data;
    if (payload && typeof payload === 'object') {
      const detail = (payload as Record<string, unknown>).detail;
      if (typeof detail === 'string' && detail.trim().length > 0) {
        return detail;
      }
    }
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return fallback;
}

export async function fetchThingDescription(thingId: string): Promise<{
  document: ThingDescription;
  hash: string;
}> {
  const encodedId = encodeURIComponent(thingId);

  try {
    const response = await axios.get<ThingDescription>(
      thingsUrl(encodedId),
      {
        headers: registryServiceHeaders(),
        timeout: config.requestTimeoutMs,
      }
    );

    const document = extractThingDocument(response.data);
    const serialized = JSON.stringify(document);
    const hash = crypto.createHash('sha256').update(serialized).digest('hex');

    return { document, hash };
  } catch (error) {
    throw new Error(
      extractRegistryErrorMessage(
        error,
        `Failed to fetch Thing Description '${thingId}'`
      )
    );
  }
}

export async function pingThingCatalog(): Promise<boolean> {
  try {
    await axios.get(`${config.registryUrl}/health`, {
      timeout: Math.min(config.requestTimeoutMs, 3000),
    });
    return true;
  } catch {
    return false;
  }
}
