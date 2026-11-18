// Shared POST helper, moved from the booking feature folder.
import { request } from '../lib/api-client'

export const post = <T>(path: string, data: unknown, headers?: HeadersInit) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(data), headers })
