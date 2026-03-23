import log from '../logger/index.js';
import { annotateThingDescriptionSecurityNames } from '../runtime/credentials.js';
import { getWotClient } from '../runtime/servient.js';
import { config } from '../config/env.js';
import {
  type ContentStoreEntry,
  fetchContentBlob,
  storeContentBlob,
} from '../services/content-store-client.js';
import {
  fetchThingDescription,
  type ThingDescription,
} from '../services/thing-catalog-client.js';
import {
  decodePayloadEnvelope,
  encodeInteractionOutputPayload,
  encodePayloadEnvelope,
  normalizeBody,
} from '../services/payloads.js';
import { createRuntimeError, formatError } from '../services/errors.js';
import {
  getAffordanceDefinition,
  resolveFormIndex,
} from '../services/form-selection.js';
import { getRuntimeHealth } from '../services/runtime-health.js';

type InteractionOperation = 'read_property' | 'invoke_action';
type EncodedInteractionPayload = {
  body: Buffer;
  contentType: string;
  sourceProtocol: string;
};

const CONTENT_REF_MEDIA_TYPE = 'application/vnd.wot.content-ref+json';

function isContentRefPayload(payload: any): boolean {
  if (!payload) return false;
  const ct = String(payload.contentType || '').trim().toLowerCase();
  return ct === CONTENT_REF_MEDIA_TYPE;
}

async function resolveContentRefInput(payload: any): Promise<any> {
  const body = normalizeBody(payload.body);
  if (body.length === 0) return payload;

  let contentRef: string;
  try {
    const parsed = JSON.parse(body.toString('utf8'));
    contentRef = typeof parsed === 'string' ? parsed : String(parsed);
  } catch {
    contentRef = body.toString('utf8').trim();
  }

  if (!contentRef) {
    throw createRuntimeError(
      'invalid_argument',
      'Content reference is empty'
    );
  }

  log.info(`Resolving content ref '${contentRef}' for action input`);
  const resolved = await fetchContentBlob(contentRef);
  return {
    body: resolved.payload,
    contentType: resolved.contentType,
  };
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function getRequestedThingId(request: any): string {
  return String(request?.target?.thingId || request?.thingId || '').trim();
}

function decodeUriVariables(uriVariables: any[] | undefined): Record<string, unknown> {
  const entries = Array.isArray(uriVariables) ? uriVariables : [];
  const values: Record<string, unknown> = {};

  for (const entry of entries) {
    const name = String(entry?.name || '').trim();
    if (!name) {
      continue;
    }
    values[name] = decodePayloadEnvelope(entry.value);
  }

  return values;
}

function buildInteractionOptions(
  request: any,
  resolvedFormIndex?: number
): Record<string, unknown> | undefined {
  const options: Record<string, unknown> = {};
  const uriVariables = decodeUriVariables(request.uriVariables);

  if (Object.keys(uriVariables).length > 0) {
    options.uriVariables = uriVariables;
  }

  const formIndex = resolvedFormIndex ?? request?.formSelector?.formIndex;
  if (typeof formIndex === 'number' && Number.isInteger(formIndex)) {
    options.formIndex = formIndex;
  }

  return Object.keys(options).length === 0 ? undefined : options;
}

function buildEncodedInteractionResponse(
  payload: { body: Buffer; contentType: string },
  responseContentType?: string
): { response: any } {
  const normalizedResponseContentType =
    responseContentType || payload.contentType || 'application/json';

  return {
    response: {
      payload: {
        body: payload.body,
        contentType: payload.contentType,
      },
      responseContentType: normalizedResponseContentType,
      matchedAdditionalResponse: false,
      success: true,
      statusCode: 200,
      statusText: 'ok',
      chosenForm: {},
    },
  };
}

function buildInteractionResponse(
  value: unknown,
  contentType?: string
): { response: any } {
  const payload = encodePayloadEnvelope(value, contentType);
  return buildEncodedInteractionResponse(
    {
      body: normalizeBody(payload.body),
      contentType: String(payload.contentType || contentType || 'application/json'),
    },
    contentType || String(payload.contentType || 'application/json')
  );
}

function buildContentRefHandle(entry: ContentStoreEntry): {
  body: Buffer;
  contentType: string;
} {
  const payload = encodePayloadEnvelope(
    {
      kind: 'content_ref',
      content_ref: entry.content_ref,
      content_type: entry.content_type,
      size_bytes: entry.size_bytes,
      digest: entry.digest,
      filename: entry.filename,
      created_at: entry.created_at,
      expires_at: entry.expires_at,
      ttl_seconds: entry.ttl_seconds,
      source: entry.source,
      metadata: entry.metadata,
      preview: entry.preview,
      detail_url: entry.detail_url,
      download_url: entry.download_url,
    },
    CONTENT_REF_MEDIA_TYPE
  );

  return {
    body: normalizeBody(payload.body),
    contentType: CONTENT_REF_MEDIA_TYPE,
  };
}

async function buildOffloadAwareInteractionResponse(
  payload: EncodedInteractionPayload,
  context: {
    thingId: string;
    affordanceName: string;
    operation: InteractionOperation;
    tdHash: string;
  }
): Promise<{ response: any }> {
  if (payload.body.length <= config.inlinePayloadMaxBytes) {
    return buildEncodedInteractionResponse(
      {
        body: payload.body,
        contentType: payload.contentType,
      },
      payload.contentType
    );
  }

  const metadata: Record<string, unknown> = {
    thing_id: context.thingId,
    affordance_name: context.affordanceName,
    operation: context.operation,
    thing_description_hash: context.tdHash,
    original_content_type: payload.contentType,
    inline_threshold_bytes: config.inlinePayloadMaxBytes,
  };

  if (payload.sourceProtocol) {
    metadata.source_protocol = payload.sourceProtocol;
  }

  try {
    const entry = await storeContentBlob({
      payload: payload.body,
      contentType: payload.contentType,
      ttlSeconds:
        config.offloadedPayloadTtlSeconds > 0
          ? config.offloadedPayloadTtlSeconds
          : undefined,
      source: `wot_runtime.${context.operation}`,
      metadata,
    });

    return buildEncodedInteractionResponse(
      buildContentRefHandle(entry),
      CONTENT_REF_MEDIA_TYPE
    );
  } catch (error) {
    log.warn(
      `Failed to offload oversized ${context.operation} output for '${context.thingId}/${context.affordanceName}', returning inline payload: ${formatError(error)}`,
    );
    return buildEncodedInteractionResponse(
      {
        body: payload.body,
        contentType: payload.contentType,
      },
      payload.contentType
    );
  }
}

async function consumeThing(request: any): Promise<{
  thing: any;
  document: ThingDescription;
  hash: string;
}> {
  const thingId = getRequestedThingId(request);
  if (!thingId) {
    throw createRuntimeError('invalid_argument', 'thing_id is required');
  }

  const { document, hash } = await fetchThingDescription(thingId).catch((error) => {
    throw createRuntimeError('not_found', formatError(error));
  });

  annotateThingDescriptionSecurityNames(document);
  const wot = await getWotClient();
  const thing = await wot.consume(document);

  return { thing, document, hash };
}

export async function handleGetThingDescription(request: any): Promise<any> {
  const thingId = String(request?.thingId || '').trim();
  if (!thingId) {
    throw createRuntimeError('invalid_argument', 'thing_id is required');
  }

  const { document, hash } = await fetchThingDescription(thingId).catch((error) => {
    throw createRuntimeError('not_found', formatError(error));
  });

  return {
    thingId,
    thingDescription: encodePayloadEnvelope(document, 'application/td+json'),
    tdHash: hash,
  };
}

export async function handleReadProperty(request: any): Promise<any> {
  const thingId = getRequestedThingId(request);
  const propertyName = String(request?.target?.affordanceName || '').trim();
  if (!propertyName) {
    throw createRuntimeError(
      'invalid_argument',
      'target.affordance_name is required for ReadProperty'
    );
  }

  const { thing, document, hash } = await consumeThing(request);
  if (!getAffordanceDefinition(document, propertyName, 'readproperty')) {
    throw createRuntimeError(
      'not_found',
      `Thing '${thingId}' does not define property '${propertyName}'`
    );
  }

  const resolvedFormIndex = (() => {
    try {
      return resolveFormIndex(
        document,
        propertyName,
        'readproperty',
        request?.formSelector
      );
    } catch (error) {
      throw createRuntimeError('invalid_argument', formatError(error));
    }
  })();

  const options = buildInteractionOptions(request, resolvedFormIndex);
  const result = await thing.readProperty(propertyName, options);

  const payload = await encodeInteractionOutputPayload(result, {
    onInvalidSchema: () => {
      log.warn(
        `Property '${propertyName}' returned data that failed schema validation, returning raw value`,
      );
    },
  });

  return buildOffloadAwareInteractionResponse(payload, {
    thingId,
    affordanceName: propertyName,
    operation: 'read_property',
    tdHash: hash,
  });
}

export async function handleWriteProperty(request: any): Promise<any> {
  const thingId = getRequestedThingId(request);
  const propertyName = String(request?.target?.affordanceName || '').trim();
  if (!propertyName) {
    throw createRuntimeError(
      'invalid_argument',
      'target.affordance_name is required for WriteProperty'
    );
  }

  const resolvedWriteInput = isContentRefPayload(request.input)
    ? await resolveContentRefInput(request.input)
    : request.input;
  const input = decodePayloadEnvelope(resolvedWriteInput);
  if (input === undefined) {
    throw createRuntimeError(
      'invalid_argument',
      'input payload is required for WriteProperty'
    );
  }

  const { thing, document } = await consumeThing(request);
  if (!getAffordanceDefinition(document, propertyName, 'writeproperty')) {
    throw createRuntimeError(
      'not_found',
      `Thing '${thingId}' does not define property '${propertyName}'`
    );
  }

  const resolvedFormIndex = (() => {
    try {
      return resolveFormIndex(
        document,
        propertyName,
        'writeproperty',
        request?.formSelector
      );
    } catch (error) {
      throw createRuntimeError('invalid_argument', formatError(error));
    }
  })();

  const options = buildInteractionOptions(request, resolvedFormIndex);
  await thing.writeProperty(propertyName, input, options);

  return buildInteractionResponse(undefined);
}

export async function handleInvokeAction(request: any): Promise<any> {
  const thingId = getRequestedThingId(request);
  const actionName = String(request?.target?.affordanceName || '').trim();
  if (!actionName) {
    throw createRuntimeError(
      'invalid_argument',
      'target.affordance_name is required for InvokeAction'
    );
  }

  const { thing, document, hash } = await consumeThing(request);
  if (!getAffordanceDefinition(document, actionName, 'invokeaction')) {
    throw createRuntimeError(
      'not_found',
      `Thing '${thingId}' does not define action '${actionName}'`
    );
  }

  const resolvedFormIndex = (() => {
    try {
      return resolveFormIndex(
        document,
        actionName,
        'invokeaction',
        request?.formSelector
      );
    } catch (error) {
      throw createRuntimeError('invalid_argument', formatError(error));
    }
  })();

  const options = buildInteractionOptions(request, resolvedFormIndex) || {};
  const resolvedInput = isContentRefPayload(request.input)
    ? await resolveContentRefInput(request.input)
    : request.input;
  const input = decodePayloadEnvelope(resolvedInput);
  const actionDef = getAffordanceDefinition(document, actionName, 'invokeaction');

  if (
    isPlainObject(actionDef) &&
    actionDef.synchronous === false
  ) {
    throw createRuntimeError(
      'unimplemented',
      `Action '${actionName}' declares synchronous=false and query/cancel support is not implemented yet`
    );
  }

  const result =
    input === undefined
      ? await thing.invokeAction(actionName, undefined, options)
      : await thing.invokeAction(actionName, input, options);

  if (result) {
    const payload = await encodeInteractionOutputPayload(result, {
      onInvalidSchema: () => {
        log.warn(
          `Action '${actionName}' returned data that failed output schema validation, returning raw value`,
        );
      },
    });
    return {
      completedResult: (
        await buildOffloadAwareInteractionResponse(payload, {
          thingId,
          affordanceName: actionName,
          operation: 'invoke_action',
          tdHash: hash,
        })
      ).response,
    };
  }

  return {
    completedResult: buildInteractionResponse(undefined).response,
  };
}

export async function handleGetRuntimeHealth(): Promise<any> {
  const health = await getRuntimeHealth();

  return {
    status: health.status,
    servientReady: health.servientReady,
    backendReachable: health.backendReachable,
    valkeyConfigured: health.valkeyConfigured,
    protocols: health.protocols,
    startedAt: health.startedAt || '',
  };
}
