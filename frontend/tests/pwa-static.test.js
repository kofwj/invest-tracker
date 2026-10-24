import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

describe('PWA & 移动端主屏幕应用静态配置校验', () => {
    const rootDir = path.resolve(__dirname, '..');
    const repoRootDir = path.resolve(rootDir, '..');
    const publicDir = path.join(rootDir, 'public');
    const indexHtmlPath = path.join(rootDir, 'index.html');
    const mainJsPath = path.join(rootDir, 'src/main.js');
    const manifestPath = path.join(publicDir, 'manifest.webmanifest');
    const swPath = path.join(publicDir, 'sw.js');
    const stylesPath = path.join(rootDir, 'src/styles/styles.css');
    const versionPyPath = path.join(repoRootDir, 'backend/version.py');

    it('manifest.webmanifest 存在、语法合法且包含 PWA 必要字段', () => {
        expect(fs.existsSync(manifestPath)).toBe(true);
        const manifestRaw = fs.readFileSync(manifestPath, 'utf-8');
        const manifest = JSON.parse(manifestRaw);

        expect(manifest.name).toBe('Invest Tracker · 真仓账本');
        expect(manifest.short_name).toBe('投资看板');
        expect(manifest.display).toBe('standalone');
        expect(manifest.start_url).toBe('/');
        expect(Array.isArray(manifest.icons)).toBe(true);
        expect(manifest.icons.length).toBeGreaterThanOrEqual(2);

        const sizes = manifest.icons.map(i => i.sizes);
        expect(sizes).toContain('192x192');
        expect(sizes).toContain('512x512');
    });

    it('PWA 图标文件在 public 目录中完整就绪', () => {
        const requiredIcons = [
            'favicon.ico',
            'apple-touch-icon.png',
            'pwa-192x192.png',
            'pwa-512x512.png',
        ];
        for (const icon of requiredIcons) {
            const iconPath = path.join(publicDir, icon);
            expect(fs.existsSync(iconPath), `缺失图标文件: ${icon}`).toBe(true);
            const stat = fs.statSync(iconPath);
            expect(stat.size).toBeGreaterThan(100);
        }
    });

    it('Service Worker CACHE_NAME 必须与 backend/version.py 严格一致', () => {
        expect(fs.existsSync(swPath)).toBe(true);
        expect(fs.existsSync(versionPyPath)).toBe(true);

        const versionPy = fs.readFileSync(versionPyPath, 'utf-8');
        const match = versionPy.match(/APP_VERSION\s*=\s*["']([^"']+)["']/);
        expect(match, '未能从 backend/version.py 解析到 APP_VERSION').not.toBeNull();
        const appVersion = match[1];

        const swContent = fs.readFileSync(swPath, 'utf-8');
        expect(swContent).toContain(`const CACHE_NAME = 'invest-tracker-v${appVersion}';`);
    });

    it('Service Worker 遵循 P1 修复规则：导航走网络优先，/ 与 /index.html 绝不进缓存优先名单', () => {
        expect(fs.existsSync(swPath)).toBe(true);
        const swContent = fs.readFileSync(swPath, 'utf-8');

        // STATIC_ASSETS 只能放不可变图标与静态清单，绝不能把 / 或 /index.html 当做缓存优先
        const staticAssetsMatch = swContent.match(/const STATIC_ASSETS\s*=\s*\[([\s\S]*?)\];/);
        expect(staticAssetsMatch).not.toBeNull();
        const staticAssetsBody = staticAssetsMatch[1];
        expect(staticAssetsBody).not.toMatch(/['"]\/['"]/);
        expect(staticAssetsBody).not.toMatch(/['"]\/index\.html['"]/);

        // 导航请求（request.mode === 'navigate'）必须先于静态资源优先分支处理
        const navIndex = swContent.indexOf("request.mode === 'navigate'");
        const staticAssetIndex = swContent.indexOf("STATIC_ASSETS.includes");
        expect(navIndex).toBeGreaterThan(0);
        expect(staticAssetIndex).toBeGreaterThan(0);
        expect(navIndex, '页面导航判定必须排在静态资源缓存优先分支之前').toBeLessThan(staticAssetIndex);

        // 核心约束：财务数据绝对不能被 SW HTTP Cache 拦住
        expect(swContent).toContain("request.method !== 'GET'");
        expect(swContent).toMatch(/url\.pathname\.startsWith\(['"]\/api['"]\)/);
        expect(swContent).toContain("url.pathname === '/health'");
    });

    it('main.js 遵循 P2 规则：桌面外壳与本地环境跳过 SW 注册并注销旧实例', () => {
        expect(fs.existsSync(mainJsPath)).toBe(true);
        const mainContent = fs.readFileSync(mainJsPath, 'utf-8');

        expect(mainContent).toContain('window.__TAURI_INTERNALS__');
        expect(mainContent).toContain("window.location.hostname === '127.0.0.1'");
        expect(mainContent).toContain('registration.unregister()');
    });

    it('index.html 正确声明 viewport-fit=cover、manifest 与 iOS Safari 全屏配置', () => {
        const html = fs.readFileSync(indexHtmlPath, 'utf-8');

        expect(html).toContain('viewport-fit=cover');
        expect(html).toContain('rel="manifest" href="/manifest.webmanifest"');
        expect(html).toContain('name="apple-mobile-web-app-capable" content="yes"');
        expect(html).toContain('name="apple-mobile-web-app-status-bar-style" content="black-translucent"');
        expect(html).toContain('name="apple-mobile-web-app-title" content="投资看板"');
        expect(html).toContain('name="theme-color"');
    });

    it('styles.css 包含刘海屏/安全区 safe-area 适配规则', () => {
        const css = fs.readFileSync(stylesPath, 'utf-8');

        expect(css).toContain('env(safe-area-inset-top');
        expect(css).toContain('env(safe-area-inset-bottom');
        expect(css).toContain('-webkit-tap-highlight-color: transparent');
    });
});
