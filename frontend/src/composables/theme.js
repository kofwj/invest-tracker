import { computed, onMounted, onUnmounted, ref } from 'vue';

const STORAGE_KEY = 'invest_tracker_theme';
const MODES = ['system', 'light', 'dark'];

function readStoredMode() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (MODES.includes(v)) return v;
  } catch (_) {
    /* ignore */
  }
  return 'system';
}

function systemPrefersDark() {
  return typeof window !== 'undefined'
    && window.matchMedia
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function createThemeController() {
  const themeMode = ref(readStoredMode());
  const systemDark = ref(systemPrefersDark());

  const resolvedTheme = computed(() => {
    if (themeMode.value === 'system') return systemDark.value ? 'dark' : 'light';
    return themeMode.value;
  });

  const themeLabel = computed(() => {
    if (themeMode.value === 'system') return '跟随系统';
    if (themeMode.value === 'dark') return '夜间';
    return '白天';
  });

  function applyTheme() {
    const root = document.documentElement;
    const dark = resolvedTheme.value === 'dark';
    root.dataset.theme = resolvedTheme.value;
    root.classList.toggle('dark', dark);
    root.style.colorScheme = dark ? 'dark' : 'light';
  }

  function setThemeMode(mode) {
    if (!MODES.includes(mode)) return;
    themeMode.value = mode;
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch (_) {
      /* ignore */
    }
    applyTheme();
  }

  function cycleThemeMode() {
    const idx = MODES.indexOf(themeMode.value);
    setThemeMode(MODES[(idx + 1) % MODES.length]);
  }

  let media;
  let onChange;

  function setupThemeListeners() {
    applyTheme();
    if (!window.matchMedia) return;
    media = window.matchMedia('(prefers-color-scheme: dark)');
    onChange = (e) => {
      systemDark.value = !!e.matches;
      if (themeMode.value === 'system') applyTheme();
    };
    if (media.addEventListener) media.addEventListener('change', onChange);
    else if (media.addListener) media.addListener(onChange);
  }

  function teardownThemeListeners() {
    if (!media || !onChange) return;
    if (media.removeEventListener) media.removeEventListener('change', onChange);
    else if (media.removeListener) media.removeListener(onChange);
  }

  // apply ASAP for first paint after mount
  if (typeof document !== 'undefined') {
    applyTheme();
  }

  return {
    themeMode,
    resolvedTheme,
    themeLabel,
    setThemeMode,
    cycleThemeMode,
    setupThemeListeners,
    teardownThemeListeners,
    applyTheme,
  };
}

/** Optional helper if a component wants local lifecycle binding. */
export function useThemeLifecycle(controller) {
  onMounted(() => controller.setupThemeListeners());
  onUnmounted(() => controller.teardownThemeListeners());
  return controller;
}
