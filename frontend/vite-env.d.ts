/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string | undefined;
  readonly VITE_SENTRY_DSN: string | undefined;
  readonly VITE_SENTRY_ENVIRONMENT: string | undefined;
  readonly VITE_SENTRY_TRACES_SAMPLE_RATE: string | undefined;
  readonly VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE: string | undefined;
  readonly VITE_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE: string | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
