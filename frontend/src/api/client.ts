// Sprint 3 (2026-10-27): shared POST helper, moved from the booking feature folder.
import { request } from '../lib/api-client'

export const post = <T>(path: string, data: unknown, headers?: HeadersInit) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(data), headers })
