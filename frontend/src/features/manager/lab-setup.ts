// Sprint 3 (1.16.0): form helpers for Lab setup (LabSetupPage.tsx).
import type { Requirement, RequirementInput } from '../../api/types/index.ts'

export function emptyRequirement(): RequirementInput {
  return { name: '', description: '', how_to_complete: '', accepted_evidence: '', reviewer: '', contact: '' }
}

export function requirementToInput(requirement: Requirement): RequirementInput {
  return {
    name: requirement.name, description: requirement.description,
    how_to_complete: requirement.how_to_complete ?? '', accepted_evidence: requirement.accepted_evidence ?? '',
    reviewer: requirement.reviewer ?? '', contact: requirement.contact ?? '',
  }
}

/** Only the texts that changed, so an edit sends (and audits) just those. */
export function requirementChanges(before: RequirementInput, after: RequirementInput): Partial<RequirementInput> {
  const changes: Partial<RequirementInput> = {}
  for (const key of Object.keys(after) as (keyof RequirementInput)[]) {
    if (before[key] !== after[key]) changes[key] = after[key]
  }
  return changes
}
