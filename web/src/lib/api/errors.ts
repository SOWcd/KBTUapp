import type { ApiError } from './types';

export class ApiErr extends Error {
  constructor(public code: ApiError['error'], message?: string, public data: Record<string, unknown> = {}) { super(message || code); }
}

/** The request never reached the server (no network, the server down). */
export const unreachable = (e: unknown): boolean => e instanceof ApiErr && e.code === 'unavailable' && e.message === 'network';
