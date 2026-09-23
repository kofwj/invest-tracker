/**
 * 模板引用的标识符必须在 <script setup> 里真实存在。
 *
 * 起因：给顶栏加 `refreshCurrentTab` 时误把解构里的 `goTab` 覆盖掉了，
 * 结果是"点标题栏不跳转"——模板里引用了 script 里不存在的名字，
 * **vite build 不会失败**，只有点下去才抛 ReferenceError。
 * 这里用官方编译器做静态校验：先取 <script setup> 的 bindings，
 * 再编译模板，任何落回 `_ctx.xxx` 的名字就是 script 里没有的。
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { parse, compileScript } from '@vue/compiler-sfc';
import { compile } from '@vue/compiler-dom';

const CANDIDATES = [join(process.cwd(), 'src'), join(process.cwd(), 'frontend', 'src')];
const SRC = CANDIDATES.find((p) => existsSync(p));
if (!SRC) throw new Error(`找不到 frontend/src（试过：${CANDIDATES.join('、')}）`);

function vueFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...vueFiles(p));
    else if (name.endsWith('.vue')) out.push(p);
  }
  return out;
}

/** 这些是 Vue/应用在模板里合法可用的、不属于 script setup 的名字 */
const ALLOWED = new Set([
  '$slots', '$attrs', '$props', '$emit', '$refs', '$el', '$options',
  '$forceUpdate', '$nextTick', '$watch', '$router', '$route', // $route/$router 来自 app.use(router)
]);

function unresolvedTemplateNames(file) {
  const src = readFileSync(file, 'utf-8');
  const { descriptor } = parse(src, { filename: file });
  if (!descriptor.scriptSetup || !descriptor.template) return null; // 只校验 <script setup>

  const { bindings } = compileScript(descriptor, { id: 'bindings-check' });
  const { code } = compile(descriptor.template.content, {
    mode: 'module',
    prefixIdentifiers: true,
    bindingMetadata: bindings,
  });
  const names = new Set();
  for (const m of code.matchAll(/_ctx\.([A-Za-z_$][\w$]*)/g)) names.add(m[1]);
  return [...names].filter((n) => !ALLOWED.has(n));
}

describe('模板标识符必须存在于 script setup', () => {
  const files = vueFiles(SRC).filter((f) => f.endsWith('.vue'));

  it('扫描到的 SFC 数量符合预期（防止扫描失效导致空跑）', () => {
    expect(files.length).toBeGreaterThanOrEqual(10);
  });

  it('没有引用未定义的名字（这类错 vite build 抓不到，只在点击时炸）', () => {
    const bad = [];
    for (const f of files) {
      const names = unresolvedTemplateNames(f);
      if (names === null) continue; // 没有 <script setup>（App.vue 走 extends 注入，静态查不了）
      if (names.length) bad.push(`${relative(SRC, f)} → ${names.join(', ')}`);
    }
    expect(bad, '模板里引用了 <script setup> 中不存在的标识符').toEqual([]);
  });
});
