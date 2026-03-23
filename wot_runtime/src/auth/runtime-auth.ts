import crypto from 'node:crypto';

import { config } from '../config/env.js';

function extractBearerToken(headerValue: string | undefined): string | null {
  if (!headerValue) {
    return null;
  }

  const match = headerValue.trim().match(/^Bearer\s+(.+)$/i);
  if (!match) {
    return null;
  }

  const token = match[1]?.trim();
  return token ? token : null;
}

function tokensMatch(candidate: string | null): boolean {
  if (!candidate) {
    return false;
  }

  const left = Buffer.from(candidate, 'utf8');
  const right = Buffer.from(config.runtimeApiToken, 'utf8');
  if (left.length !== right.length) {
    return false;
  }

  return crypto.timingSafeEqual(left, right);
}

export function requestHasRuntimeApiToken(request: { get(name: string): string | undefined }): boolean {
  return tokensMatch(extractBearerToken(request.get('authorization')));
}
