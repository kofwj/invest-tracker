import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

describe('PWA & 移动端主屏幕应用静态配置校验', () => {
    const rootDir = path.resolve(__dirname, '..');
    const publicDir = path.join(rootDir, 'public');
    const indexHtmlPath = path.join(rootDir, 'index.html');
    const manifestPath = path.join(publicDir, 'manifest.webmanifest');
    const swPath = path.join(publicDir, 'sw.js');
    const stylesPath = path.join(rootDir, 'src/styles/styles.css');

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

    it('Service Worker 存在且绝不对 /api 进行财务数据缓存', () => {
        expect(fs.existsSync(swPath)).toBe(true);
        const swContent = fs.readFileSync(swPath, 'utf-8');

        expect(swContent).toContain('addEventListener(\'install\'');
        expect(swContent).toContain('addEventListener(\'activate\'');
        expect(swContent).toContain('addEventListener(\'fetch\'');

        // 核心约束：财务数据绝对不能被 SW HTTP Cache 拦住
        expect(swContent).toMatch(/\/api/);
        expect(swContent).toContain('request.method !== \'GET\'');
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
