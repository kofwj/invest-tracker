const createSnapshotsModule = ({
    activeTab,
    snapshots,
    snapshotRange,
    snapshotSummary,
    snapshotMetrics,
    snapshotChangeRows,
    snapshotLoading,
    fetchData,
    nextTick,
}) => {
    const createSnapshot = async () => {
        snapshotLoading.value = true;
        try {
            const res = await api.createSnapshot();
            const action = res.data?.action === 'updated' ? '已更新今日快照' : '今日快照已记录';
            ElementPlus.ElMessage.success(action);
            await fetchData();
            await fetchSnapshots();
        } catch (e) {
            const detail = e?.response?.data?.detail || e?.message || '记录失败';
            ElementPlus.ElMessage.error(detail);
        } finally {
            snapshotLoading.value = false;
        }
    };

    const buildSnapshotAnalysis = () => {
        const rowsAsc = [...snapshots.value].sort((a, b) => String(a.date).localeCompare(String(b.date)));
        if (!rowsAsc.length) {
            snapshotMetrics.value = [];
            snapshotChangeRows.value = [];
            return;
        }
        const first = rowsAsc[0];
        const last = rowsAsc[rowsAsc.length - 1];
        const change = key => Number(last[key] || 0) - Number(first[key] || 0);
        const changePct = key => Number(first[key] || 0) ? (Number(last[key] || 0) / Number(first[key]) - 1) * 100 : null;
        const totalChange = change('total_assets');
        const profitChange = change('total_profit');
        const investRatio = Number(last.total_assets || 0) ? Number(last.total_market_value || 0) / Number(last.total_assets) * 100 : 0;
        const liquidRatio = Number(last.total_assets || 0) ? (Number(last.bank_balance || 0) + Number(last.securities_cash || 0) + Number(last.pending_purchase || 0)) / Number(last.total_assets) * 100 : 0;
        snapshotMetrics.value = [
            { key: 'latest', label: '最新总资产', value: formatMoney(last.total_assets), sub: `${last.date}，${last.holdings_count || 0} 个持仓` },
            { key: 'change', label: '区间总资产变化', value: formatMoney(totalChange, 2, true), sub: changePct('total_assets') === null ? '无期初基数' : `${changePct('total_assets') >= 0 ? '+' : ''}${changePct('total_assets').toFixed(2)}%`, color: totalChange >= 0 ? '#F56C6C' : '#67C23A' },
            { key: 'profit', label: '投资盈亏变化', value: formatMoney(profitChange, 2, true), sub: `当前累计 ${formatMoney(last.total_profit)}`, color: profitChange >= 0 ? '#F56C6C' : '#67C23A' },
            { key: 'ratio', label: '当前投资 / 流动占比', value: `${investRatio.toFixed(1)}%`, sub: `现金+存款+在途 ${liquidRatio.toFixed(1)}%` },
        ];
        const labels = {
            total_assets: '总资产',
            total_market_value: '投资账户市值',
            bank_balance: '银行存款',
            securities_cash: '证券现金',
            total_profit: '投资盈亏',
            pending_purchase: '申购在途',
        };
        snapshotChangeRows.value = rowsAsc.length >= 2 ? Object.keys(labels).map(key => ({
            label: labels[key],
            start: Number(first[key] || 0),
            end: Number(last[key] || 0),
            change: change(key),
            change_pct: changePct(key),
        })) : [];
    };

    const renderSnapshotCharts = () => renderSnapshotChartsView(snapshots.value);

    const fetchSnapshots = async () => {
        try {
            const res = await api.listSnapshots(snapshotRange.value);
            snapshots.value = res.data;
            if (snapshotRange.value && snapshotRange.value.length === 2) {
                const summaryRes = await api.snapshotSummary(snapshotRange.value);
                snapshotSummary.value = summaryRes.data;
            } else {
                snapshotSummary.value = null;
            }
            buildSnapshotAnalysis();
            if (activeTab.value === 'snapshots') nextTick(renderSnapshotCharts);
        } catch (e) { console.error('获取快照失败', e); }
    };

    return { createSnapshot, buildSnapshotAnalysis, renderSnapshotCharts, fetchSnapshots };
};

window.createSnapshotsModule = createSnapshotsModule;
