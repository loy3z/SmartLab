export const MAX_EVIDENCE_BYTES = 5 * 1024 * 1024

export function evidenceProblem(file: { name: string; size: number } | null): string {
  if (!file) return 'Upload your training certificate to continue.'
  if (file.size === 0) return 'The selected file is empty. Choose a training certificate.'
  if (file.size > MAX_EVIDENCE_BYTES) return 'The file must be no larger than 5 MiB.'
  if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) return 'Please choose a PDF, PNG or JPEG file.'
  return ''
}
