/**
 * Detect node-wot DataSchemaError by duck-typing.
 *
 * The class sets its prototype to NotSupportedError (a known node-wot bug),
 * so `instanceof DataSchemaError` is unreliable.  We check the message and
 * the presence of a `.value` property instead.
 */
export function isDataSchemaError(error: unknown): error is Error & { value: unknown } {
  return error instanceof Error && error.message === 'Invalid value according to DataSchema' && 'value' in error;
}

export type RuntimeErrorCode =
  | 'invalid_argument'
  | 'not_found'
  | 'failed_precondition'
  | 'deadline_exceeded'
  | 'unimplemented'
  | 'permission_denied'
  | 'unauthenticated'
  | 'already_exists'
  | 'resource_exhausted'
  | 'internal'
  | 'unknown';

const HTTP_STATUS_BY_RUNTIME_ERROR_CODE: Record<RuntimeErrorCode, number> = {
  invalid_argument: 400,
  not_found: 404,
  failed_precondition: 412,
  deadline_exceeded: 504,
  unimplemented: 501,
  permission_denied: 403,
  unauthenticated: 401,
  already_exists: 409,
  resource_exhausted: 429,
  internal: 500,
  unknown: 500,
};

export class RuntimeError extends Error {
  code: RuntimeErrorCode;
  status: number;
  details: string;

  constructor(code: RuntimeErrorCode, message: string) {
    super(message);
    this.name = 'RuntimeError';
    this.code = code;
    this.status = HTTP_STATUS_BY_RUNTIME_ERROR_CODE[code];
    this.details = message;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function createRuntimeError(code: RuntimeErrorCode, message: string): RuntimeError {
  return new RuntimeError(code, message);
}

export function isRuntimeError(error: unknown): error is RuntimeError {
  return error instanceof RuntimeError;
}

export function getRuntimeErrorStatus(error: unknown): number {
  return isRuntimeError(error) ? error.status : 500;
}

export function getRuntimeErrorCode(error: unknown): RuntimeErrorCode | 'unknown' {
  return isRuntimeError(error) ? error.code : 'unknown';
}

export function formatError(error: unknown): string {
  if (error instanceof Error) {
    return error.message || error.name || 'Unknown error';
  }

  if (typeof error === 'string') {
    return error;
  }

  if (isRecord(error)) {
    const details = typeof error.details === 'string' && error.details.trim() ? error.details.trim() : null;
    const message = typeof error.message === 'string' && error.message.trim() ? error.message.trim() : null;
    const name = typeof error.name === 'string' && error.name.trim() ? error.name.trim() : null;
    const code = typeof error.code === 'number' || typeof error.code === 'string' ? String(error.code) : null;
    const base = details || message;

    if (base) {
      const prefix = name && name !== base ? `${name}: ` : '';
      const suffix = code ? ` (code ${code})` : '';
      return `${prefix}${base}${suffix}`;
    }

    try {
      return JSON.stringify(error);
    } catch {
      return 'Unknown error';
    }
  }

  return String(error);
}
