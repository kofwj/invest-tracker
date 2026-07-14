<template>
  <el-config-provider :locale="zhCn">
    <div class="app-container">
      <AppHeader />
      <HomeDashboard />

      <el-tabs v-model="activeTab" class="mt-20">
        <el-tab-pane label="资产快照" name="snapshots" lazy>
          <SnapshotsTab />
        </el-tab-pane>
        <el-tab-pane label="资产配置" name="allocation" lazy>
          <AllocationTab />
        </el-tab-pane>
        <el-tab-pane label="收益分析" name="performance" lazy>
          <PerformanceTab />
        </el-tab-pane>
        <el-tab-pane label="市场摘要" name="market" lazy>
          <MarketTab />
        </el-tab-pane>
        <el-tab-pane label="纪律与再平衡" name="discipline" lazy>
          <DisciplineTab />
        </el-tab-pane>
        <el-tab-pane label="持仓明细" name="holdings" lazy>
          <HoldingsTab />
        </el-tab-pane>
        <el-tab-pane label="银行存款" name="deposits" lazy>
          <DepositsTab />
        </el-tab-pane>
        <el-tab-pane label="交易录入/管理" name="transactions" lazy>
          <TransactionsTab />
        </el-tab-pane>
        <el-tab-pane label="现金设置" name="cash" lazy>
          <CashTab />
        </el-tab-pane>
        <el-tab-pane label="数据维护" name="maintenance" lazy>
          <MaintenanceTab />
        </el-tab-pane>
      </el-tabs>

      <AppDialogs />
      <LoginOverlay />
    </div>
  </el-config-provider>
</template>

<script>
import { defineAsyncComponent } from 'vue';
import AppHeader from './components/AppHeader.vue';
import HomeDashboard from './components/HomeDashboard.vue';
import AppDialogs from './components/AppDialogs.vue';
import LoginOverlay from './components/LoginOverlay.vue';

export default {
  name: 'App',
  components: {
    AppHeader,
    HomeDashboard,
    AppDialogs,
    LoginOverlay,
    SnapshotsTab: defineAsyncComponent(() => import('./views/SnapshotsTab.vue')),
    AllocationTab: defineAsyncComponent(() => import('./views/AllocationTab.vue')),
    PerformanceTab: defineAsyncComponent(() => import('./views/PerformanceTab.vue')),
    MarketTab: defineAsyncComponent(() => import('./views/MarketTab.vue')),
    DisciplineTab: defineAsyncComponent(() => import('./views/DisciplineTab.vue')),
    HoldingsTab: defineAsyncComponent(() => import('./views/HoldingsTab.vue')),
    DepositsTab: defineAsyncComponent(() => import('./views/DepositsTab.vue')),
    TransactionsTab: defineAsyncComponent(() => import('./views/TransactionsTab.vue')),
    CashTab: defineAsyncComponent(() => import('./views/CashTab.vue')),
    MaintenanceTab: defineAsyncComponent(() => import('./views/MaintenanceTab.vue')),
  },
};
</script>
