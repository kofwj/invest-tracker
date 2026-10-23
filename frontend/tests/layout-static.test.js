/**
 * 布局静态检查（窄屏可读性 + 页头不重复）。
 *
 * 起因三条，都是"构建不会失败、肉眼在宽屏上也不会发现"的问题：
 *  1) 10 张 ≥8 列的表没冻结首列，窄屏横向滚动后看不到行标识（最宽 12 列 / 1182px）；
 *  2) 顶栏一行里塞了品牌 + 4 个分组 + 主题 + 刷新 + 同步价 + 退出，没有断点（@media 数量 0）；
 *  3) 12 个页面用 <PageShell title="收益分析">，标题文字与页内 tab 完全重复 —— 同一个词连出两行。
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

// vitest 在 jsdom 下 import.meta.url 不是 file://，所以从 cwd 找 src，
// 同时容忍从仓库根目录执行（frontend/src）。
const CANDIDATES = [join(process.cwd(), 'src'), join(process.cwd(), 'frontend', 'src')];
const SRC = CANDIDATES.find((p) => existsSync(p));
if (!SRC) throw new Error(`找不到 frontend/src（试过：${CANDIDATES.join('、')}）`);

const CSS_FILE = join(SRC, 'styles', 'styles.css');
const VIEWS_DIR = join(SRC, 'views');

function walk(dir, ext) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p, ext));
    else if (name.endsWith(ext)) out.push(p);
  }
  return out;
}

/** 每张 <el-table>（排除 <el-table-column>）→ {line, columnCount, firstColumnLine, firstColumnTag} */
function tables(src) {
  const out = [];
  const re = /<el-table(?![-/\w])/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    const start = m.index;
    const close = src.indexOf('</el-table>', start);
    const block = close === -1 ? src.slice(start) : src.slice(start, close);
    const line = src.slice(0, start).split('\n').length;

    const cols = [...block.matchAll(/<el-table-column(?![\w-])/g)];
    let firstColumnTag = null;
    let firstColumnLine = null;
    if (cols.length) {
      const colStart = cols[0].index;
      const tagEnd = block.indexOf('>', colStart);
      firstColumnTag = tagEnd === -1 ? block.slice(colStart) : block.slice(colStart, tagEnd + 1);
      firstColumnLine = line + block.slice(0, colStart).split('\n').length - 1;
    }
    out.push({ line, columnCount: cols.length, firstColumnLine, firstColumnTag });
  }
  return out;
}

const tableEntries = walk(SRC, '.vue').flatMap((f) =>
  tables(readFileSync(f, 'utf-8')).map((t) => ({ file: relative(SRC, f), ...t })),
);
const wideTables = tableEntries.filter((t) => t.columnCount >= 8);

describe('宽表冻结首列', () => {
  it('扫描到的 ≥8 列表数量符合预期（防止正则失效导致下面的检查空跑）', () => {
    expect(wideTables.length).toBeGreaterThanOrEqual(10);
  });

  it('列数 ≥8 的表格，第一个 <el-table-column> 必须 fixed="left"', () => {
    const missing = wideTables.filter(
      (t) => !t.firstColumnTag || !/fixed\s*=\s*"left"/.test(t.firstColumnTag),
    );
    expect(
      missing.map((t) => `${t.file}:${t.firstColumnLine}（${t.columnCount} 列）`),
      '窄屏横向滚动后看不到行标识：给这些表的第一列加 fixed="left"',
    ).toEqual([]);
  });
});

/** 按大括号配平切出每个 @media 块 */
function mediaBlocks(css) {
  const out = [];
  const re = /@media[^{]*\{/g;
  let m;
  while ((m = re.exec(css)) !== null) {
    const header = css.slice(m.index, re.lastIndex - 1).trim();
    let depth = 1;
    let i = re.lastIndex;
    while (i < css.length && depth > 0) {
      if (css[i] === '{') depth += 1;
      else if (css[i] === '}') depth -= 1;
      i += 1;
    }
    out.push({ header, body: css.slice(re.lastIndex, i - 1) });
    re.lastIndex = i;
  }
  return out;
}

describe('顶栏响应式', () => {
  const css = readFileSync(CSS_FILE, 'utf-8');
  const blocks = mediaBlocks(css);

  it('styles.css 里有针对 .header 的 @media 断点', () => {
    const headerBlocks = blocks.filter((b) => /\.header\s*[,{]/.test(b.body));
    expect(
      headerBlocks.map((b) => b.header),
      '顶栏一行塞满按钮却没有断点：至少要有 ≤900px / ≤640px 两处',
    ).not.toEqual([]);
  });

  it('≤900px 隐藏品牌副标题与主题文字（只留图标）', () => {
    const b = blocks.find((x) => /max-width:\s*900px/.test(x.header));
    expect(b, '缺少 ≤900px 断点').toBeTruthy();
    expect(/\.header-subtitle[^{]*\{[^}]*display:\s*none/.test(b.body)).toBe(true);
    expect(/\.header-theme-label[^{]*\{[^}]*display:\s*none/.test(b.body)).toBe(true);
  });

  it('≤640px 顶栏排成两行 grid，第 2 行分组导航可横向滚动', () => {
    // 断点收敛后 640 这一档有很多块，所以要挑出真正动顶栏的那个
    const candidates = blocks.filter((x) => /max-width:\s*640px/.test(x.header));
    expect(candidates.length, '缺少 ≤640px 断点').toBeGreaterThan(0);
    expect(
      candidates.some((b) => /\.header\s*\{[^}]*display:\s*grid/.test(b.body)),
      '.header 在 ≤640px 要排成两行 grid',
    ).toBe(true);
    expect(
      candidates.some((b) => /\.header-nav\s*\{[^}]*overflow-x:\s*auto/.test(b.body)),
      '窄屏分组导航要横向可滚动（隐藏滚动条）',
    ).toBe(true);
  });
});

describe('页头不再和 tab 重复', () => {
  it('views 里的 <PageShell> 不再传 title（可见标题与 tab 重复两行）', () => {
    const bad = [];
    for (const f of walk(VIEWS_DIR, '.vue')) {
      const src = readFileSync(f, 'utf-8');
      for (const tag of src.matchAll(/<PageShell\b[^>]*>/g)) {
        if (/title\s*=/.test(tag[0])) bad.push(`${relative(SRC, f)} → ${tag[0].replace(/\s+/g, ' ')}`);
      }
    }
    expect(bad, '页头标题交给 PageShell 里的隐藏 h1，不要再传 title prop').toEqual([]);
  });
});

/**
 * 总览页指标栅格。
 *
 * 起因：`.overview-metrics` 原来写死 3 列、主卡 `grid-column: 1 / -1` 独占一整行，
 * 而「今天」有 3 张卡、「资产与仓位」有 5 张 → 两段的行尾都会空出格子
 * （今天空 1 格、资产空 2 格），主卡还占满 1240px 只放一个数字。
 *
 * 按原型重排后：「资产」段 = 四个等权数字一行（发丝线分格，没有主卡），
 * 「今天」不再是指标栅格而是左右两栏的卡（左今日盈亏 / 右待办）。
 * 两条不变量照旧钉住：**列数按段指定** + **每档断点用同特异性选择器覆盖**。
 */
describe('总览页指标栅格', () => {
  const src = readFileSync(join(VIEWS_DIR, 'OverviewTab.vue'), 'utf-8');

  it('列数按段指定（资产 4 个数字一行；今天卡左右两栏）', () => {
    expect(src, '「资产」段应为 4 轨（总资产 / 持仓浮盈 / 现金+存款 / 权益·防御）')
      .toMatch(/\[data-section="assets"\]\s+\.overview-metrics\s*\{[^}]*repeat\(4/);
    expect(src, '「今天」卡应为左右两栏（左今日盈亏 / 右待办）')
      .toMatch(/\.ov-today\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)/);
  });

  it('每档断点用同特异性选择器覆盖，否则桌面规则会压住媒体查询', () => {
    const mq = src.slice(src.indexOf('@media (max-width: 1100px)'));
    expect(mq, '≤1100px 必须用 [data-section=…] 选择器').toContain('[data-section="assets"] .overview-metrics');
    expect(mq, '≤1100px 今天卡要塌成一列').toContain('.ov-today');
  });

  it('窄屏发丝线不在行首：单列时左侧分隔线全部去掉', () => {
    const small = src.slice(src.indexOf('@media (max-width: 640px)'));
    expect(small, '单列必须真的塌成一列').toMatch(
      /\[data-section="assets"\]\s+\.overview-metrics\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/,
    );
    expect(small, '单列时左侧发丝线会挂在行首，必须去掉').toMatch(
      /\[data-section="assets"\]\s+\.ov-metric\s*\+\s*\.ov-metric\s*\{[^}]*border-left:\s*0/,
    );
  });
});

/**
 * 模板 class 不许「有引用没定义」：写了 class 就要有样式定义，否则删掉。
 * 只检查静态 class="…"；`:class` 绑定的名字来自数据，静态分析判不了。
 */
describe('模板 class 不许「有引用没定义」', () => {
  it('src 下每个 <template> 里静态写的 class 都能在 styles.css 或某个 style 块里找到定义', () => {
    const vueFiles = walk(SRC, '.vue');
    const cssText = readFileSync(CSS_FILE, 'utf-8');
    const scoped = [];
    for (const f of vueFiles) {
      const src = readFileSync(f, 'utf-8');
      const i = src.indexOf('<style');
      if (i !== -1) scoped.push(src.slice(i));
    }
    const defined = new Set(
      [...[cssText, ...scoped].join('\n').matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)].map((m) => m[1]),
    );

    const missing = new Set();
    for (const f of vueFiles) {
      // 切到 <script> 为止：不能用首个 </template>（嵌套的 <template #header> 会提前截断，
      // 后面的区块就漏检了 —— 「观察与预警」那行就是这么漏过去的）
      const src = readFileSync(f, 'utf-8');
      const scriptAt = src.indexOf('<script');
      const tpl = scriptAt === -1 ? src : src.slice(0, scriptAt);
      for (const m of tpl.matchAll(/\sclass="([^"]*)"/g)) {
        for (const token of m[1].split(/\s+/).filter(Boolean)) {
          if (!defined.has(token)) missing.add(`${relative(SRC, f)} → .${token}`);
        }
      }
    }
    expect([...missing].sort(), '这些 class 没有任何样式定义：要么补样式，要么把死标记删掉').toEqual([]);
  });
});

/** 应用外壳吸顶：滚动时顶栏不消失、二级导航仍可切页 */
describe('应用外壳吸顶', () => {
  const css = readFileSync(CSS_FILE, 'utf-8');

  it('顶栏吸顶在视口顶部（滚长页面时分组导航不再消失）', () => {
    expect(css, '.header 要 position: sticky + top: 0').toMatch(/\.header\s*\{[^}]*position:\s*sticky/);
    expect(css, '.header 吸顶后要压在页面内容之上').toMatch(/\.header\s*\{[^}]*z-index:\s*var\(--z-header\)/);
  });

  it('二级导航吸在顶栏下方（原来它属于页面内容，一滚就没）', () => {
    expect(css).toMatch(/\.page-shell-header\s*\{[^}]*position:\s*sticky/);
    expect(css, '吸顶位置要跟着顶栏高度走，不能写死数字')
      .toMatch(/\.page-shell-header\s*\{[^}]*top:\s*var\(--app-shell-header-h/);
  });

  it('吸顶的二级导航自带底色，否则内容会从 content-shell 内边距的缝隙里透出来', () => {
    expect(css).toMatch(/\.page-shell-header::before\s*\{[^}]*background:\s*var\(--app-surface\)/);
    expect(css, '外扩宽度要跟着 content-shell 的左右内边距').toMatch(/inset:\s*0\s+calc\(-1 \* var\(--shell-pad-x/);
  });
});

/**
 * 断点只有三档：1100 / 900 / 640。
 *
 * 收敛前全仓有 10 个不同值（560/640/720/768/800/900/960/1000/1100/1280），
 * 每一处都是「当时看着不顺眼就加一个」，结果同一个布局意图在相邻宽度上表现不一致，
 * 也没人说得清某个宽度到底走哪一套规则。这里把它钉成可执行的不变量。
 */
describe('断点只有三档', () => {
  const ALLOWED = [1100, 900, 640];
  const files = [CSS_FILE, ...walk(SRC, '.vue')];
  const widthsOf = (src) =>
    [...src.matchAll(/@media[^{]*\(max-width:\s*(\d+)px/g)].map((m) => ({
      width: Number(m[1]),
      line: src.slice(0, m.index).split('\n').length,
    }));

  it(`所有 @media (max-width) 只能是 ${ALLOWED.join(' / ')}`, () => {
    const bad = [];
    for (const f of files) {
      for (const { width, line } of widthsOf(readFileSync(f, 'utf-8'))) {
        if (!ALLOWED.includes(width)) bad.push(`${relative(SRC, f)}:${line} → ${width}px`);
      }
    }
    expect(bad, '断点收敛到 1100 / 900 / 640 三档，别再新增第四档').toEqual([]);
  });

  it('三档都真的在用（防止收敛后某一档变成死规则）', () => {
    const used = new Set();
    for (const f of files) {
      for (const { width } of widthsOf(readFileSync(f, 'utf-8'))) used.add(width);
    }
    expect([...used].sort((a, b) => b - a)).toEqual(ALLOWED);
  });
});
