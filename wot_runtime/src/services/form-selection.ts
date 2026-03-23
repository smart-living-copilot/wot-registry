import type { ThingDescription } from './thing-catalog-client.js';

type JsonRecord = Record<string, unknown>;

export type AffordanceOperation =
  | 'readproperty'
  | 'writeproperty'
  | 'observeproperty'
  | 'invokeaction'
  | 'subscribeevent';

type NormalizedFormSelector = {
  formIndex?: number;
  href?: string;
  preferredScheme?: string;
  preferredContentType?: string;
  preferredSubprotocol?: string;
};

function isPlainObject(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function cleanString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeMediaType(value: unknown): string {
  const raw = cleanString(value).toLowerCase();
  return raw.split(';', 1)[0] || '';
}

function normalizeStringArray(value: unknown): string[] {
  if (typeof value === 'string') {
    const cleaned = cleanString(value).toLowerCase();
    return cleaned ? [cleaned] : [];
  }

  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => cleanString(item).toLowerCase())
    .filter((item) => item.length > 0);
}

function extractScheme(href: string): string {
  try {
    return new URL(href).protocol.replace(/:$/, '').toLowerCase();
  } catch {
    const match = href.match(/^([a-z][a-z0-9+.-]*):/i);
    return match ? match[1].toLowerCase() : '';
  }
}

function normalizeFormSelector(formSelector: unknown): NormalizedFormSelector | null {
  if (!isPlainObject(formSelector)) {
    return null;
  }

  const formIndex = formSelector.formIndex;
  const normalized: NormalizedFormSelector = {};

  if (typeof formIndex === 'number' && Number.isInteger(formIndex) && formIndex >= 0) {
    normalized.formIndex = formIndex;
  }

  const href = cleanString(formSelector.href);
  if (href) {
    normalized.href = href;
  }

  const preferredScheme = cleanString(formSelector.preferredScheme).toLowerCase();
  if (preferredScheme) {
    normalized.preferredScheme = preferredScheme;
  }

  const preferredContentType = normalizeMediaType(formSelector.preferredContentType);
  if (preferredContentType) {
    normalized.preferredContentType = preferredContentType;
  }

  const preferredSubprotocol = cleanString(formSelector.preferredSubprotocol).toLowerCase();
  if (preferredSubprotocol) {
    normalized.preferredSubprotocol = preferredSubprotocol;
  }

  return Object.keys(normalized).length > 0 ? normalized : null;
}

function operationSection(operation: AffordanceOperation): 'properties' | 'actions' | 'events' {
  if (operation === 'invokeaction') {
    return 'actions';
  }
  if (operation === 'subscribeevent') {
    return 'events';
  }
  return 'properties';
}

function thingIdFromDocument(document: ThingDescription): string {
  const thingId = cleanString(document.id);
  return thingId || 'unknown';
}

export function getAffordanceDefinition(
  document: ThingDescription,
  affordanceName: string,
  operation: AffordanceOperation
): JsonRecord | null {
  const section = document[operationSection(operation)];
  if (!isPlainObject(section)) {
    return null;
  }

  const affordance = section[affordanceName];
  return isPlainObject(affordance) ? affordance : null;
}

function getAffordanceForms(
  document: ThingDescription,
  affordanceName: string,
  operation: AffordanceOperation
): JsonRecord[] {
  const affordance = getAffordanceDefinition(document, affordanceName, operation);
  if (!affordance || !Array.isArray(affordance.forms)) {
    return [];
  }

  return affordance.forms.filter(isPlainObject);
}

function formSupportsOperation(form: JsonRecord, operation: AffordanceOperation): boolean {
  const operations = normalizeStringArray(form.op);
  return operations.length === 0 || operations.includes(operation);
}

function formMatchesSelector(
  form: JsonRecord,
  formIndex: number,
  selector: NormalizedFormSelector,
  operation: AffordanceOperation
): boolean {
  if (selector.formIndex !== undefined && selector.formIndex !== formIndex) {
    return false;
  }

  if (!formSupportsOperation(form, operation)) {
    return false;
  }

  if (selector.href && cleanString(form.href) !== selector.href) {
    return false;
  }

  if (selector.preferredScheme) {
    const scheme = extractScheme(cleanString(form.href));
    if (scheme !== selector.preferredScheme) {
      return false;
    }
  }

  if (selector.preferredContentType) {
    const contentType = normalizeMediaType(form.contentType);
    if (contentType !== selector.preferredContentType) {
      return false;
    }
  }

  if (selector.preferredSubprotocol) {
    const subprotocols = normalizeStringArray(form.subprotocol);
    if (!subprotocols.includes(selector.preferredSubprotocol)) {
      return false;
    }
  }

  return true;
}

export function resolveFormIndex(
  document: ThingDescription,
  affordanceName: string,
  operation: AffordanceOperation,
  formSelector: unknown
): number | undefined {
  const selector = normalizeFormSelector(formSelector);
  if (!selector) {
    return undefined;
  }

  const forms = getAffordanceForms(document, affordanceName, operation);
  const matchedIndex = forms.findIndex((form, index) =>
    formMatchesSelector(form, index, selector, operation)
  );

  if (matchedIndex >= 0) {
    return matchedIndex;
  }

  const thingId = thingIdFromDocument(document);
  throw new Error(
    `No form matched the requested selector for '${operation}' on Thing '${thingId}' affordance '${affordanceName}'`
  );
}
