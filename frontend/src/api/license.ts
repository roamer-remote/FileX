import api from './index'

export interface LicenseStatus {
  valid: boolean
  reason: string | null
  expires_at: string | null
  customer_id: string | null
  days_remaining: number | null
  in_trial: boolean
  license_key_masked: string | null
}

export interface LicenseAdminStatus extends LicenseStatus {
  license_hmac_secret: string | null
  license_hmac_secret_effective: string | null
}

export interface LicenseActivateBody {
  license_key: string
  admin_username: string
  admin_password: string
}

export function getLicenseStatus(config?: { skipErrorToast?: boolean }) {
  return api.get<LicenseStatus>('/license/status', {
    skipErrorToast: config?.skipErrorToast,
    skipAuthRedirect: true,
  })
}

export function activateLicense(body: LicenseActivateBody) {
  return api.post<LicenseStatus>('/license/activate', body, {
    skipAuthRedirect: true,
    skipErrorToast: true,
  })
}

export function getAdminLicense() {
  return api.get<LicenseAdminStatus>('/admin/license')
}

export function putAdminLicense(license_key: string) {
  return api.put<LicenseAdminStatus>('/admin/license', { license_key }, {
    skipErrorToast: true,
  })
}

export const LICENSE_INVALID_EVENT = 'filex-license-invalid'

export function dispatchLicenseInvalidEvent(): void {
  window.dispatchEvent(new CustomEvent(LICENSE_INVALID_EVENT))
}
