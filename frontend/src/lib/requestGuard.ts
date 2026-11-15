/**
 * Monotonic request sequence + AbortController guard & structured HTTP error classifier.
 * Prevents slow out-of-order responses from overwriting newer UI state (Prompt 22 Section 11).
 */

export interface GuardToken {
  seq: number;
  signal: AbortSignal | undefined;
}

export interface ChannelGuard {
  next: () => GuardToken;
  isCurrent: (seq: number) => boolean;
  abort: () => void;
}

export function createChannelGuard(): ChannelGuard {
  let latestSeq = 0;
  let controller: AbortController | null = null;

  return {
    next(): GuardToken {
      if (controller) {
        controller.abort();
      }
      latestSeq += 1;
      controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      return {
        seq: latestSeq,
        signal: controller?.signal,
      };
    },
    isCurrent(seq: number): boolean {
      return seq === latestSeq;
    },
    abort(): void {
      latestSeq += 1;
      if (controller) {
        controller.abort();
        controller = null;
      }
    },
  };
}

export function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === "AbortError";
}

export function classifyHttpError(status: number, detail: string): string {
  const clean = detail.trim();
  if (status === 409) {
    return `CONFLICT (HTTP 409): Plan version or idempotency conflict — refresh or recompute before retrying. ${clean}`;
  }
  if (status === 401 || status === 403) {
    return `AUTH_REQUIRED (HTTP ${status}): Operator token missing or invalid for protected action. ${clean}`;
  }
  if (status === 422) {
    return `VALIDATION_OR_STALE (HTTP 422): ${clean}`;
  }
  if (status === 404) {
    return `NOT_FOUND (HTTP 404): ${clean}`;
  }
  return `HTTP ${status}: ${clean}`;
}

export async function parseApiError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const rawDetail =
      typeof body?.detail === "string"
        ? body.detail
        : body?.detail !== undefined
        ? JSON.stringify(body.detail)
        : JSON.stringify(body);
    return classifyHttpError(res.status, rawDetail || fallback);
  } catch {
    return classifyHttpError(res.status, fallback);
  }
}
