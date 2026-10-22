import type { ApiError } from './types';

export class ApiErr extends Error {
  constructor(public code: ApiError['error'], message?: string, public data: Record<string, unknown> = {}) { super(message || code); }
}
