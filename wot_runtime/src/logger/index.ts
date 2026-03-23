const timestamp = (): string => new Date().toISOString();

function logWithLevel(
  level: 'INFO' | 'ERROR' | 'DEBUG' | 'WARN',
  message: string,
  ...args: unknown[]
): void {
  const line = `[${level}] ${timestamp()} - ${message}`;
  if (level === 'ERROR') {
    console.error(line, ...args);
    return;
  }

  console.log(line, ...args);
}

const log = {
  info: (message: string, ...args: unknown[]) =>
    logWithLevel('INFO', message, ...args),
  warn: (message: string, ...args: unknown[]) =>
    logWithLevel('WARN', message, ...args),
  error: (message: string, ...args: unknown[]) =>
    logWithLevel('ERROR', message, ...args),
  debug: (message: string, ...args: unknown[]) =>
    logWithLevel('DEBUG', message, ...args),
};

export default log;
