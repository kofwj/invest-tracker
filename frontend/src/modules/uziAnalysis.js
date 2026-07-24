/**
 * UZI-Skill 混合模式集成（本机 Hermes 执行）
 * 功能：把 invest-tracker 的真实持仓数据打包成高质量 prompt，供用户复制到本地 Hermes 执行。
 * 备忘仅存浏览器 localStorage，不入真仓。
 */

const NOTES_KEY = 'invest-tracker-uzi-notes-v1';

export const UZI_FOCUS_TEMPLATES = [
    { key: 'default', label: '综合分析', hint: '完整深度分析' },
    { key: 'portfolio_risk', label: '组合风险', hint: '这只票在组合里的风险与集中度' },
    { key: 'today_attr', label: '今日归因', hint: '今天涨跌对组合的影响' },
    { key: 'add_reduce', label: '加仓/减仓', hint: '结合成本仓位给操作参考' },
    { key: 'data_check', label: '数据对账', hint: '核对数量成本是否可信' },
];

function loadAllNotes() {
    try {
        const raw = localStorage.getItem(NOTES_KEY);
        if (!raw) return {};
        const obj = JSON.parse(raw);
        return obj && typeof obj === 'object' ? obj : {};
    } catch (_) {
        return {};
    }
}

export function loadUziNote(code) {
    const c = String(code || '').trim();
    if (!c) return '';
    const all = loadAllNotes();
    const item = all[c];
    return item?.text || '';
}

export function saveUziNote(code, text) {
    const c = String(code || '').trim();
    if (!c) return false;
    const all = loadAllNotes();
    const t = String(text || '').trim();
    if (!t) {
        delete all[c];
    } else {
        all[c] = { text: t, updated_at: new Date().toISOString() };
    }
    try {
        localStorage.setItem(NOTES_KEY, JSON.stringify(all));
        return true;
    } catch (_) {
        return false;
    }
}

function focusInstruction(focusKey) {
    switch (focusKey) {
        case 'portfolio_risk':
            return [
                '【本次重点：组合风险】',
                '- 结合我当前仓位占比与浮盈，判断这只票是不是拖累/过度集中',
                '- 说明若继续持有，组合层面最大风险是什么',
                '- 不要泛泛谈行业，要落到「我的仓位」',
            ].join('\n');
        case 'today_attr':
            return [
                '【本次重点：今日归因】',
                '- 结合最新价与我的持仓市值，粗判它对组合今日盈亏的影响方向',
                '- 区分「标的自身波动」和「我该不该因此动作」',
                '- 若信息不足就明说，不要编造盘中细节',
            ].join('\n');
        case 'add_reduce':
            return [
                '【本次重点：加仓 / 减仓参考】',
                '- 必须结合普通成本、摊薄成本、浮盈和仓位占比',
                '- 给出：继续持有 / 分批减 / 暂不加 的条件（用价格或比例说话）',
                '- 明确这是分析参考，不是下单指令',
            ].join('\n');
        case 'data_check':
            return [
                '【本次重点：数据对账】',
                '- 根据我提供的数量、成本、分红，指出哪些字段最容易和券商对不上',
                '- 给出我去券商页核对时的检查清单（3-5 条）',
                '- 不要建议自动改仓，只说怎么人工核对',
            ].join('\n');
        default:
            return '【本次重点：综合深度分析】结合真实持仓给出可执行结论。';
    }
}

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

    const buildPrompt = (row, depth = 'medium', focusKey = 'default') => {
        if (!row || !row.code) return '';

        const total = Number(dashboard?.value?.total_assets || dashboard?.total_assets || 0);
        const qty = Number(row.quantity || 0);
        const price = Number(row.last_price || 0);
        const mv = qty * price;
        const weight = total > 0 ? (mv / total * 100) : 0;
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

        const focus = focusInstruction(focusKey);
        const note = loadUziNote(row.code);
        const noteBlock = note
            ? `\n【我之前的分析备忘（仅供参考，可能过时）】\n${note}\n`
            : '';

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
${noteBlock}
${focus}

推荐执行命令：
python run.py ${row.code} --depth ${depth}

（或直接对 Hermes 说：“用 ${depth} 模式深度分析 ${row.code}”）

严格要求（请遵守 UZI-Skill 硬性规则）：
1. 必须呈现不同评委/流派的分歧与冲突，不要和稀泥
2. 必须引用具体数据、规则和估值模型输出
3. **必须结合我当前的真实持仓成本、浮盈和仓位比例**进行判断（不是泛泛分析这只票）
4. 给出清晰的风险点、催化剂和操作参考
5. 禁止空话术（“基本面良好”“值得关注”等）
6. 这是只读分析：不要假设会自动下单或修改账本

请输出完整的自包含 HTML 报告 + 一段关键结论摘要。`;
    };

    return {
        buildUziPrompt: buildPrompt,
        templates: UZI_FOCUS_TEMPLATES,
        loadUziNote,
        saveUziNote,
    };
}
