import { inject } from 'vue';

export const APP_CTX_KEY = Symbol('invest-tracker-app-ctx');

export function useAppCtx() {
  const ctx = inject(APP_CTX_KEY);
  if (!ctx) {
    throw new Error('useAppCtx() must be used under App root provide');
  }
  return ctx;
}
