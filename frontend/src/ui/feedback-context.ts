import { createContext, useContext } from 'react'

export type ToastTone = 'success' | 'error' | 'info'

export interface ConfirmOptions {
  title: string
  /** Body text or a short list of facts shown under the title. */
  message?: string
  details?: { label: string; value: string }[]
  confirmLabel?: string
  cancelLabel?: string
  /** Red confirm button for destructive actions (cancel, reject, close a room). */
  danger?: boolean
  /** Ask for a reason in the dialog; the confirm button stays disabled until one is entered. */
  reason?: { label: string; placeholder?: string; required?: boolean; maxLength?: number }
}

export interface ConfirmResult {
  confirmed: boolean
  reason: string
}

export interface Feedback {
  success: (message: string, title?: string) => void
  error: (message: string, title?: string) => void
  info: (message: string, title?: string) => void
  /** Resolves when the user confirms or cancels. Never rejects. */
  confirm: (options: ConfirmOptions) => Promise<ConfirmResult>
}

export const FeedbackContext = createContext<Feedback | null>(null)

/** Toasts and confirmation dialogs shared by every page (one implementation, consistent look). */
export function useFeedback(): Feedback {
  const value = useContext(FeedbackContext)
  if (!value) throw new Error('useFeedback must be used inside <FeedbackProvider>.')
  return value
}
