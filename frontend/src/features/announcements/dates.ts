// Sprint 3 (1.19.0): datetime-local controls display Sydney wall time, independent of the device zone.
import { TZ } from '../booking/format.ts'

export function dateTimeInput(iso: string | null): string {
  if (!iso) return ''
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(iso))
  const value = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return `${value.year}-${value.month}-${value.day}T${value.hour}:${value.minute}`
}

export function dateTimeISO(value: string): string | null {
  if (!value) return null
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error('Choose a valid date and time.')
  const target = Date.parse(`${value}:00Z`)
  let guess = target
  for (let attempt = 0; attempt < 3; attempt++) {
    const shown = Date.parse(`${dateTimeInput(new Date(guess).toISOString())}:00Z`)
    guess += target - shown
  }
  if (dateTimeInput(new Date(guess).toISOString()) !== value) throw new Error('This time does not exist in Sydney. Choose another time.')
  return new Date(guess).toISOString()
}
