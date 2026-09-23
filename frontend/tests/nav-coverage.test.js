/**
 * 导航分组覆盖静态检查。
 *
 * 起因：券商对账 /broker 与资产快照 /snapshots 有路由、页面也在，但没挂进任何分组，
 * 界面上完全点不到（而「资产快照」是每日收益的数据源）。
 * 这里把「每个有路由的页面必须挂到某个分组，或者明确是已重定向的旧页」钉住：
 * 以后新增页面忘了挂分组，这条会直接变红。
 */
import { describe, it, expect } from 'vitest';
import { ROUTE_META, TAB_GROUPS, LEGACY_TAB_REDIRECT } from '../src/modules/tabNav.js';

const groupOf = new Map();
for (const g of TAB_GROUPS) {
  for (const t of g.tabs) {
    if (!groupOf.has(t)) groupOf.set(t, []);
    groupOf.get(t).push(g.id);
  }
}

describe('导航分组覆盖', () => {
  it('分组结构本身是合法的（防止下面几条空跑）', () => {
    expect(TAB_GROUPS.length).toBeGreaterThanOrEqual(3);
    expect(Object.keys(ROUTE_META).length).toBeGreaterThanOrEqual(10);
  });

  it('每个路由要么挂在某个分组的 tabs 里，要么在 LEGACY_TAB_REDIRECT 里', () => {
    const orphans = Object.keys(ROUTE_META).filter(
      (key) => !groupOf.has(key) && !(key in LEGACY_TAB_REDIRECT),
    );
    expect(
      orphans,
      '这些页面有路由但界面上点不到：挂进 TAB_GROUPS，或确认它是被重定向的旧页再放进 LEGACY_TAB_REDIRECT',
    ).toEqual([]);
  });

  it('被重定向的旧页在新分组里不用出现（否则就是没重定向干净）', () => {
    const stillGrouped = Object.keys(LEGACY_TAB_REDIRECT).filter((old) => groupOf.has(old));
    expect(stillGrouped, '旧页面同时挂在分组里会让人不知道点哪个').toEqual([]);
  });

  it('分组里的每个 tab 都有路由元信息（否则 tabLabel 只能回退成英文 key）', () => {
    const unknown = [];
    for (const g of TAB_GROUPS) {
      for (const t of g.tabs) {
        if (!ROUTE_META[t]) unknown.push(`${g.id}/${t}`);
      }
    }
    expect(unknown).toEqual([]);
  });

  it('同一个分组内不能有重复项', () => {
    const dup = [];
    for (const g of TAB_GROUPS) {
      const seen = new Set();
      for (const t of g.tabs) {
        if (seen.has(t)) dup.push(`${g.id}/${t}`);
        seen.add(t);
      }
    }
    expect(dup).toEqual([]);
  });

  it('同一个页面不能同时属于两个分组', () => {
    const dup = [...groupOf.entries()].filter(([, ids]) => ids.length > 1);
    expect(dup.map(([tab, ids]) => `${tab} → ${ids.join(', ')}`)).toEqual([]);
  });

  it('两个曾经失联的页面确实挂在了分组里', () => {
    expect(groupOf.has('broker'), '券商对账 /broker 又变成孤儿页了').toBe(true);
    expect(groupOf.has('snapshots'), '资产快照 /snapshots 又变成孤儿页了').toBe(true);
  });
});
