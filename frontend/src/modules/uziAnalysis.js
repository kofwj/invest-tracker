/**
 * UZI-Skill 混合模式集成（本机 Hermes 执行）
 * 功能：把 invest-tracker 的真实持仓数据打包成高质量 prompt，供用户复制到本地 Hermes 执行。
 */

export function createUziAnalysisHelper({ dashboard, formatMoney }) {
    const money = (value, digits = 2, showSign = false) => {
        if (typeof formatMoney === 'function') {
            try {
                return formatMoney(value, digits, showSign);
            } catch (_) {
                // fall through
            }
        }
        const num = Number(value);
        if (Number.isNaN(num)) return '—';
        const sign = showSign && num > 0 ? '+' : (num < 0 ? '-' : '');
        return `${sign}¥${Math.abs(num).toFixed(digits)}`;
    };

    const buildPrompt = (row, depth = 'medium') => {
        if (!row || !row.code) return '';

        const total = Number(dashboard?.value?.total_assets || dashboard?.total_assets || 0);
        const qty = Number(row.quantity || 0);
        const price = Number(row.last_price || 0);
        const mv = qty * price;
        const weight = total > 0 ? (mv / total * 100) : 0;
        // 后端可能不直接给 float_profit，这里兜底自己算
        const floatProfit = Number(
            row.float_profit != null
                ? row.float_profit
                : ((price - Number(row.avg_cost || 0)) * qty + Number(row.total_dividend || 0))
        );

        const depthLabel = depth === 'lite'
            ? 'lite（1-2分钟快速判断）'
            : depth === 'deep'
                ? 'deep（15-20分钟，含 Bull-Bear 辩论）'
                : 'medium（推荐，5-8分钟）';

        return `请使用 UZI-Skill 对以下标的进行 **${depthLabel}** 分析：

股票：${row.name || ''} (${row.code})，分类：${row.category || '未分类'}

【我的真实持仓信息（请重点结合我的实际成本和仓位比例给出针对性判断）】
- 持仓数量：${qty}
- 普通成本：${money(row.avg_cost, 4)}
- 摊薄成本：${money(row.diluted_cost, 4)}
- 当前最新价：${money(price, 4)}
- 当前市值：${money(mv)}
- 持仓浮盈：${money(floatProfit, 2, true)}
- 占组合总资产比例：约 ${weight.toFixed(2)}%
- 当前总资产参考：${money(total)}

推荐执行命令：
python run.py ${row.code} --depth ${depth}

（或直接对 Hermes 说：“用 ${depth} 模式深度分析 ${row.code}”）

严格要求（请遵守 UZI-Skill 硬性规则）：
1. 必须呈现不同评委/流派的分歧与冲突，不要和稀泥
2. 必须引用具体数据、规则和估值模型输出
3. **必须结合我当前的真实持仓成本、浮盈和仓位比例**进行判断（不是泛泛分析这只票）
4. 给出清晰的风险点、催化剂和操作参考
5. 禁止空话术（“基本面良好”“值得关注”等）

请输出完整的自包含 HTML 报告 + 一段关键结论摘要。`;
    };

    return {
        buildUziPrompt: buildPrompt,
    };
}
