export const RUNTIME_SECURITY_NAME_FIELD = '__wotRegistrySecurityName';

type PlainObject = Record<string, unknown>;

export type RuntimeCredentialEntry = {
  security_name: string;
  scheme: string;
  credentials: PlainObject;
};

export type RuntimeThingSecrets = {
  entries: RuntimeCredentialEntry[];
};

type RuntimeSecretsTarget = {
  addCredentials: (credentials: Record<string, RuntimeThingSecrets>) => void;
  credentialStore?: Map<string, unknown[]>;
};

type ClientSecurityPatchTarget = {
  prototype: {
    setSecurity?: (metadata: unknown, credentials: unknown) => unknown;
  };
};

type SecurityMetadata = PlainObject & {
  scheme?: string;
};

const patchedSecurityTargets = new WeakSet<object>();

function isPlainObject(value: unknown): value is PlainObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isRuntimeCredentialEntry(value: unknown): value is RuntimeCredentialEntry {
  return (
    isPlainObject(value) &&
    typeof value.security_name === 'string' &&
    typeof value.scheme === 'string' &&
    isPlainObject(value.credentials)
  );
}

function isRuntimeThingSecrets(value: unknown): value is RuntimeThingSecrets {
  return (
    isPlainObject(value) &&
    Array.isArray(value.entries) &&
    value.entries.every((entry) => isRuntimeCredentialEntry(entry))
  );
}

function unwrapRuntimeThingSecrets(value: unknown): RuntimeThingSecrets | undefined {
  if (isRuntimeThingSecrets(value)) {
    return value;
  }

  if (Array.isArray(value) && value.length === 1 && isRuntimeThingSecrets(value[0])) {
    return value[0];
  }

  return undefined;
}

function getPrimarySecurityMetadata(metadata: unknown): SecurityMetadata | undefined {
  if (!Array.isArray(metadata) || metadata.length === 0) {
    return undefined;
  }

  const security = metadata[0];
  if (!isPlainObject(security)) {
    return undefined;
  }

  return security as SecurityMetadata;
}

function resolveCredentialEntry(metadata: unknown, secrets: RuntimeThingSecrets): RuntimeCredentialEntry | undefined {
  const security = getPrimarySecurityMetadata(metadata);
  const securityName =
    typeof security?.[RUNTIME_SECURITY_NAME_FIELD] === 'string' ? security[RUNTIME_SECURITY_NAME_FIELD] : undefined;

  if (securityName) {
    const matchingEntry = secrets.entries.find((entry) => entry.security_name === securityName);
    if (matchingEntry) {
      return matchingEntry;
    }
  }

  const scheme = typeof security?.scheme === 'string' ? security.scheme : undefined;
  if (scheme) {
    const matchingEntries = secrets.entries.filter((entry) => entry.scheme === scheme);
    if (matchingEntries.length === 1) {
      return matchingEntries[0];
    }
    if (matchingEntries.length > 1) {
      throw new Error(
        `Multiple credentials match security scheme '${scheme}' and no security-name match was available`,
      );
    }
  }

  if (secrets.entries.length === 1) {
    return secrets.entries[0];
  }

  return undefined;
}

export function resolveRuntimeCredentials(metadata: unknown, storedCredentials: unknown): PlainObject | undefined {
  const secrets = unwrapRuntimeThingSecrets(storedCredentials);
  if (!secrets) {
    if (storedCredentials === undefined) {
      return undefined;
    }
    throw new Error('wot_runtime expected runtime secrets in envelope format');
  }

  const entry = resolveCredentialEntry(metadata, secrets);
  if (entry) {
    return entry.credentials;
  }

  const security = getPrimarySecurityMetadata(metadata);
  const securityName =
    typeof security?.[RUNTIME_SECURITY_NAME_FIELD] === 'string' ? security[RUNTIME_SECURITY_NAME_FIELD] : undefined;
  const scheme = typeof security?.scheme === 'string' ? security.scheme : undefined;

  const requestedSecurity =
    securityName || scheme
      ? securityName
        ? `security definition '${securityName}'`
        : `security scheme '${scheme}'`
      : 'the requested Thing security metadata';

  throw new Error(`No credentials matched ${requestedSecurity}`);
}

export function installClientCredentialPatch(clientClass: ClientSecurityPatchTarget): void {
  const prototype = clientClass.prototype;
  if (patchedSecurityTargets.has(prototype)) {
    return;
  }

  const originalSetSecurity = prototype.setSecurity;
  if (typeof originalSetSecurity !== 'function') {
    throw new Error('Unable to install runtime credential patch for node-wot client');
  }

  prototype.setSecurity = function patchedSetSecurity(metadata: unknown, credentials: unknown): unknown {
    return originalSetSecurity.call(this, metadata, resolveRuntimeCredentials(metadata, credentials));
  };

  patchedSecurityTargets.add(prototype);
}

export function applyRuntimeSecrets(target: RuntimeSecretsTarget, secrets: Record<string, unknown>): void {
  if (target.credentialStore instanceof Map) {
    target.credentialStore.clear();
  }

  for (const [thingId, value] of Object.entries(secrets)) {
    if (!isRuntimeThingSecrets(value)) {
      throw new Error(`Invalid runtime secret payload for Thing '${thingId}'`);
    }

    target.addCredentials({ [thingId]: value });
  }
}

export function annotateThingDescriptionSecurityNames(document: Record<string, unknown>): void {
  const securityDefinitions = document.securityDefinitions;
  if (!isPlainObject(securityDefinitions)) {
    return;
  }

  for (const [securityName, definition] of Object.entries(securityDefinitions)) {
    if (!isPlainObject(definition)) {
      continue;
    }

    definition[RUNTIME_SECURITY_NAME_FIELD] = securityName;
  }
}
