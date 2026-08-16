/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_BUILD_VERSION?: string
  readonly VITE_EXTRACT_ASSET_HYDRATE_CONCURRENCY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
