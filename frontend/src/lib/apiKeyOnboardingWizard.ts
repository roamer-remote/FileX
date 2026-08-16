export type ApiKeyWizardStep = 1 | 2 | 3

/** Step 2「下一步」是否可用：复制成功，或用户走手动确认路径（由 UI 直接调 step 3） */
export function canAdvanceFromStep2(installCopySucceeded: boolean): boolean {
  return installCopySucceeded
}

export function wizardStepTitleKey(step: ApiKeyWizardStep): string {
  switch (step) {
    case 1:
      return 'apiKeyOnboardingWizard.step1Title'
    case 2:
      return 'apiKeyOnboardingWizard.step2Title'
    case 3:
      return 'apiKeyOnboardingWizard.step3Title'
    default: {
      const _exhaustive: never = step
      return _exhaustive
    }
  }
}
