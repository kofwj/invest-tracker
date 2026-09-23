/**
 * 静态可达性检查。
 *
 * 起因：全仓 33 个 <el-table> 一个都没有 aria-label，屏幕阅读器只会念"表格"，
 * 完全不知道是持仓明细还是备份列表。这种遗漏不会让构建失败、也不会让行为测试变红，
 * 所以用一条静态扫描把它钉住：以后新增表格必须带标签。
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

// vitest 在 jsdom 下 import.meta.url 不是 file://，所以从 cwd 找 src，
// 同时容忍从仓库根目录执行（frontend/src）。
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

/** <el-table>（排除 <el-table-column>）：返回 [{line, tag}] */
function tableTags(src) {
  const out = [];
  const re = /<el-table(?![-\w])/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    const end = src.indexOf('>', m.index);
    const tag = end === -1 ? src.slice(m.index) : src.slice(m.index, end + 1);
    out.push({ line: src.slice(0, m.index).split('\n').length, tag });
  }
  return out;
}

describe('表格可达性', () => {
  const files = vueFiles(SRC);
  const tables = files.flatMap((f) => tableTags(readFileSync(f, 'utf-8')).map((t) => ({
    file: relative(SRC, f),
    ...t,
  })));

  it('扫描到的表格数量符合预期（防止正则失效导致这条检查空跑）', () => {
    expect(tables.length).toBeGreaterThanOrEqual(30);
  });

  it('每个 <el-table> 都有 aria-label', () => {
    const missing = tables.filter((t) => !/aria-label\s*=/.test(t.tag));
    expect(
      missing.map((t) => `${t.file}:${t.line}`),
      '这些表格缺少 aria-label（写清它在展示什么，例如 aria-label="交易流水"）',
    ).toEqual([]);
  });

  it('aria-label 不是空串或占位符', () => {
    const bad = tables.filter((t) => {
      const m = t.tag.match(/aria-label\s*=\s*"([^"]*)"/);
      if (!m) return false; // 动态绑定由上一条兜住
      return m[1].trim().length < 2;
    });
    expect(bad.map((t) => `${t.file}:${t.line}`)).toEqual([]);
  });
});

describe('键盘焦点可见性', () => {
  it('全局样式里保留了 :focus-visible 规则（否则键盘用户看不到焦点在哪）', () => {
    const css = readFileSync(join(SRC, 'styles', 'styles.css'), 'utf-8');
    expect(css).toContain(':focus-visible');
  });
});
