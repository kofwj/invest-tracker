import { useAuthStore } from '../stores/auth.js';

export function createAuthMask({ onUnlocked } = {}) {
  const authStore = useAuthStore();
  if (onUnlocked) {
    authStore.setOnUnlocked(onUnlocked);
  }
  return authStore;
}
