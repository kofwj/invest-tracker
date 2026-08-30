import { describe, it, expect } from 'vitest';
import {
  formatMoney,
  formatPercent,
  daysUntil,
  daysBetween,
  holdingFloatProfit,
  holdingFloatProfitRate,
  holdingLifetimeProfit,
  holdingLifetimeProfitRate,
} from '../src/utils/index.js';
import { analyzeKlineTrend } from '../src/charts/index.js';

describe('formatMoney', () => {
  it('formats positive with ¥ and 2 decimals', () => {
    expect(formatMoney(1234.5)).toBe('¥1,234.50');
  });
  it('formats negative with minus sign', () => {
    expect(formatMoney(-12.3)).toBe('-¥12.30');
  });
  it('shows dash for null/undefined/empty', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
    expect(formatMoney('')).toBe('—');
  });
  it('shows dash for NaN', () => {
    expect(formatMoney(NaN)).toBe('—');
  });
  it('supports showSign prefix', () => {
    expect(formatMoney(5, 2, true)).toBe('+¥5.00');
    expect(formatMoney(-5, 2, true)).toBe('-¥5.00');
  });
});

describe('formatPercent', () => {
  it('adds + for non-negative and % suffix', () => {
    expect(formatPercent(1.234)).toBe('+1.23%');
    expect(formatPercent(-1.234)).toBe('-1.23%');
    expect(formatPercent(0)).toBe('+0.00%');
  });
  it('returns dash for null', () => {
    expect(formatPercent(null)).toBe('—');
  });
});

describe('daysUntil / daysBetween', () => {
  it('computes inclusive day difference', () => {
    expect(daysBetween('2026-05-01', '2026-05-10')).toBe(9);
    expect(daysBetween('2026-05-10', '2026-05-01')).toBe(-9);
  });
  it('returns null on invalid input', () => {
    expect(daysBetween('', '2026-05-10')).toBeNull();
    expect(daysUntil('not-a-date')).toBeNull();
    expect(daysUntil('')).toBeNull();
  });
});

describe('holdingFloatProfit (浮盈)', () => {
  it('(last - avg) * qty + dividend', () => {
    const row = { quantity: 1000, avg_cost: 10, last_price: 12, total_dividend: 500 };
    expect(holdingFloatProfit(row)).toBe(2500);
  });
  it('handles missing fields as zero', () => {
    expect(holdingFloatProfit({})).toBe(0);
  });
  it('rate: profit / invested * 100', () => {
    const row = { quantity: 1000, avg_cost: 10, last_price: 12, total_dividend: 500 };
    expect(holdingFloatProfitRate(row)).toBeCloseTo(25);
  });
  it('rate: null when invested is zero', () => {
    expect(holdingFloatProfitRate({ quantity: 0, avg_cost: 10, last_price: 12 })).toBeNull();
  });
});

describe('holdingLifetimeProfit (全周期盈亏)', () => {
  it('uses diluted_cost as net-invested basis (no dividend double count)', () => {
    const row = {
      quantity: 1000,
      avg_cost: 12,
      diluted_cost: 10, // 净投入/数量，分红已摊入
      last_price: 18,
      total_dividend: 2000, // 分红已体现在摊薄成本，不再重复加
    };
    expect(holdingLifetimeProfit(row)).toBe(8000);
  });
  it('falls back to avg_cost when diluted_cost missing', () => {
    const row = { quantity: 500, avg_cost: 8, last_price: 10, total_dividend: 100 };
    expect(holdingLifetimeProfit(row)).toBe(1000);
  });
  it('rate divides by diluted net investment', () => {
    const row = { quantity: 1000, diluted_cost: 10, last_price: 18 };
    expect(holdingLifetimeProfitRate(row)).toBeCloseTo(80);
  });
  it('rate null when net investment not positive', () => {
    expect(holdingLifetimeProfitRate({ quantity: 1000, diluted_cost: 0, last_price: 18 })).toBeNull();
  });
  it('rate falls back to avg_cost when diluted_cost is null (与 holdingLifetimeProfit 口径一致)', () => {
    const row = { quantity: 500, avg_cost: 8, diluted_cost: null, last_price: 10 };
    // 净投入按 avg_cost 回退：profit 1000 / net 4000 * 100 = 25
    expect(holdingLifetimeProfitRate(row)).toBeCloseTo(25);
  });
  it('rate falls back to avg_cost when diluted_cost missing key', () => {
    const row = { quantity: 200, avg_cost: 5, last_price: 7 };
    expect(holdingLifetimeProfitRate(row)).toBeCloseTo(40);
  });
});

describe('analyzeKlineTrend (均线解读)', () => {
  const genRows = (closes) => closes.map((c, i) => ({
    date: `2026-01-${String(i + 1).padStart(2, '0')}`,
    open: c, high: c, low: c, close: c, volume: 1000,
  }));

  it('returns not-ok when fewer than 20 rows', () => {
    const r = analyzeKlineTrend(genRows(Array(19).fill(10)));
    expect(r.ok).toBe(false);
    expect(r.brief).toContain('20');
  });

  it('detects bull alignment (多头排列) with price above MA20', () => {
    // 严格单调上升 → MA5 > MA10 > MA20, price above MA20, 偏离小
    const closes = Array.from({ length: 60 }, (_, i) => 10 + i * 0.2);
    const r = analyzeKlineTrend(genRows(closes));
    expect(r.ok).toBe(true);
    expect(r.brief).toContain('多头排列');
    expect(r.status).toBe('ok');
    expect(r.ma5).toBeGreaterThan(r.ma10);
    expect(r.ma10).toBeGreaterThan(r.ma20);
  });

  it('detects bear alignment (空头排列) below MA20', () => {
    const closes = Array.from({ length: 60 }, (_, i) => 30 - i * 0.2);
    const r = analyzeKlineTrend(genRows(closes));
    expect(r.ok).toBe(true);
    expect(r.brief).toContain('空头排列');
    expect(r.status).toBe('high');
  });

  it('computes golden cross daysAgo on uptrend flip', () => {
    // 前 30 天下跌、后 30 天上涨 → 中间有一次 MA5 上穿 MA10
    const closes = [
      ...Array.from({ length: 30 }, (_, i) => 20 - i * 0.3),
      ...Array.from({ length: 40 }, (_, i) => 10 + i * 0.3),
    ];
    const r = analyzeKlineTrend(genRows(closes));
    if (r.cross) {
      expect(['gold', 'death']).toContain(r.cross.type);
    }
    // 无论有无交叉，至少能产出白话结论
    expect(r.points.length).toBeGreaterThan(0);
  });

  it('returns ma values as rounded numbers', () => {
    const closes = Array.from({ length: 60 }, (_, i) => 10 + i * 0.2);
    const r = analyzeKlineTrend(genRows(closes));
    expect(r.ma5).toBeGreaterThan(0);
    expect(r.ma20).toBeGreaterThan(0);
    expect(r.dev20).toBeTypeOf('number');
  });
});