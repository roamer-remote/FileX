import { describe, expect, it } from 'vitest'
import { canAdvanceFromStep2, wizardStepTitleKey } from './apiKeyOnboardingWizard'

describe('apiKeyOnboardingWizard', () => {
  it('canAdvanceFromStep2 requires copy success for primary next button', () => {
    expect(canAdvanceFromStep2(false)).toBe(false)
    expect(canAdvanceFromStep2(true)).toBe(true)
  })

  it('wizardStepTitleKey maps each step', () => {
    expect(wizardStepTitleKey(1)).toBe('apiKeyOnboardingWizard.step1Title')
    expect(wizardStepTitleKey(2)).toBe('apiKeyOnboardingWizard.step2Title')
    expect(wizardStepTitleKey(3)).toBe('apiKeyOnboardingWizard.step3Title')
  })
})
