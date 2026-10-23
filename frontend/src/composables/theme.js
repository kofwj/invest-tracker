import { useThemeStore } from '../stores/theme.js';

export function createThemeController() {
  return useThemeStore();
}
