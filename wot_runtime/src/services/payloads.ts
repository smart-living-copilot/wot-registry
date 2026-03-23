import { isDataSchemaError } from './errors.js';

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function normalizeBody(body: unknown): Buffer {
  if (Buffer.isBuffer(body)) {
    return body;
  }

  if (body instanceof Uint8Array) {
    return Buffer.from(body);
  }

  if (Array.isArray(body)) {
    return Buffer.from(body);
  }

  return Buffer.alloc(0);
}

export function decodePayloadEnvelope(payload: any): unknown {
  if (!payload) {
    return undefined;
  }

  const body = normalizeBody(payload.body);
  if (body.length === 0) {
    return undefined;
  }

  const contentType = String(payload.contentType || '')
    .trim()
    .toLowerCase();
  const text = body.toString('utf8');

  if (!contentType || contentType.includes('json')) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  if (contentType.startsWith('text/')) {
    return text;
  }

  return body;
}

export function encodePayloadEnvelope(value: unknown, contentType?: string): any {
  if (value === undefined) {
    return {
      body: Buffer.alloc(0),
      contentType: contentType || 'application/json',
    };
  }

  if (Buffer.isBuffer(value) || value instanceof Uint8Array) {
    return {
      body: Buffer.from(value),
      contentType: contentType || 'application/octet-stream',
    };
  }

  if (typeof value === 'string') {
    return {
      body: Buffer.from(value, 'utf8'),
      contentType: contentType || 'text/plain; charset=utf-8',
    };
  }

  return {
    body: Buffer.from(JSON.stringify(value), 'utf8'),
    contentType: contentType || 'application/json',
  };
}

function extractContentType(form: unknown): string {
  if (!isPlainObject(form)) {
    return 'application/json';
  }

  const response = form.response;
  if (isPlainObject(response) && typeof response.contentType === 'string') {
    return response.contentType;
  }

  if (typeof form.contentType === 'string' && form.contentType.trim()) {
    return form.contentType;
  }

  return 'application/json';
}

export function extractProtocol(href: unknown): string {
  if (typeof href !== 'string' || href.trim().length === 0) {
    return '';
  }

  try {
    return new URL(href).protocol.replace(/:$/, '');
  } catch {
    return '';
  }
}

export async function encodeInteractionOutputPayload(
  output: any,
  options?: {
    onInvalidSchema?: (value: unknown) => void;
  },
): Promise<{
  body: Buffer;
  contentType: string;
  sourceProtocol: string;
}> {
  const form = output?.form;
  const contentType = extractContentType(form);
  const sourceProtocol = extractProtocol(isPlainObject(form) ? form.href : '');

  try {
    const value = await output.value();
    const payload = encodePayloadEnvelope(value, contentType);
    return {
      body: normalizeBody(payload.body),
      contentType: String(payload.contentType || contentType),
      sourceProtocol,
    };
  } catch (error) {
    if (isDataSchemaError(error)) {
      options?.onInvalidSchema?.(error.value);
      const payload = encodePayloadEnvelope(error.value, contentType);
      return {
        body: normalizeBody(payload.body),
        contentType: String(payload.contentType || contentType),
        sourceProtocol,
      };
    }

    const buffer = Buffer.from(await output.arrayBuffer());
    return {
      body: buffer,
      contentType,
      sourceProtocol,
    };
  }
}
