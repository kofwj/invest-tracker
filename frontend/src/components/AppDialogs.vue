<template>
        <!-- 交易记录弹窗 -->
        <el-dialog v-model="transDialog.visible" :title="transDialog.title" width="800px">
            <el-table :data="transDialog.transactions" stripe style="width: 100%">
                <el-table-column prop="date" label="日期" width="120"></el-table-column>
                <el-table-column prop="direction" label="方向" width="80"></el-table-column>
                <el-table-column label="数量">
                    <template #default="scope">{{ scope.row.quantity }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column label="单价">
                    <template #default="scope">{{ formatMoney(scope.row.price, 4) }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column label="金额">
                    <template #default="scope">{{ formatMoney(scope.row.amount) }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column label="手续费">
                    <template #default="scope">{{ formatMoney(scope.row.fee) }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column prop="remark" label="备注"></el-table-column>
            </el-table>
        </el-dialog>

        <!-- 存款编辑弹窗 -->
        <el-dialog v-model="depositDialog.visible" :title="depositDialog.isEdit ? '编辑存款' : '新增存款'" width="500px">
            <el-form :model="depositDialog.form" label-width="100px">
                <el-form-item label="银行名称">
                    <el-input v-model="depositDialog.form.bank_name"></el-input>
                </el-form-item>
                <el-form-item label="金额">
                    <el-input-number v-model="depositDialog.form.amount" :precision="2" :min="0" style="width: 100%"></el-input-number>
                </el-form-item>
                <el-form-item label="年利率(%)">
                    <el-input-number v-model="depositDialog.form.interest_rate" :precision="2" :min="0" style="width: 100%"></el-input-number>
                </el-form-item>
                <el-form-item label="起存日">
                    <el-date-picker v-model="depositDialog.form.start_date" type="date" placeholder="可选，算整期利息" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
                </el-form-item>
                <el-form-item label="到期时间">
                    <el-date-picker v-model="depositDialog.form.due_date" type="date" placeholder="选择到期日" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
                </el-form-item>
                <el-form-item label="备注">
                    <el-input v-model="depositDialog.form.remark"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="depositDialog.visible = false">取消</el-button>
                <el-button type="primary" @click="saveDeposit">确定</el-button>
            
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
        </el-dialog>

        <!-- 交易编辑弹窗 -->
        <el-dialog v-model="transEditDialog.visible" title="编辑交易记录" width="820px">
            <el-form :model="transEditDialog.form" label-width="90px">
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="日期">
                            <el-date-picker v-model="transEditDialog.form.date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="方向">
                            <el-select v-model="transEditDialog.form.direction" style="width: 100%">
                                <el-option label="买入" value="买入"></el-option>
                                <el-option label="卖出" value="卖出"></el-option>
                                <el-option label="分红" value="分红"></el-option>
                                <el-option label="分红再投资" value="分红再投资"></el-option>
                                <el-option label="申购待确认" value="申购待确认"></el-option>
                            </el-select>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="证券账户">
                            <el-select v-model="transEditDialog.form.account" style="width: 100%">
                                <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
                            </el-select>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12"></el-col>
                </el-row>
                <el-row :gutter="20">
                    <el-col :span="8">
                        <el-form-item label="代码">
                            <el-input v-model="transEditDialog.form.code"></el-input>
                        </el-form-item>
                    </el-col>
                    <el-col :span="10">
                        <el-form-item label="名称">
                            <el-input v-model="transEditDialog.form.name"></el-input>
                        </el-form-item>
                    </el-col>
                    <el-col :span="6">
                        <el-form-item label="分类">
                            <el-select v-model="transEditDialog.form.category" clearable style="width: 100%">
                                <el-option label="A股权益" value="A股权益"></el-option>
                                <el-option label="A股ETF" value="A股ETF"></el-option>
                                <el-option label="港股ETF" value="港股ETF"></el-option>
                                <el-option label="债基" value="债基"></el-option>
                                <el-option label="REITs" value="REITs"></el-option>
                                <el-option label="黄金" value="黄金"></el-option>
                                <el-option label="其他" value="其他"></el-option>
                            </el-select>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="数量">
                            <el-input-number v-model="transEditDialog.form.quantity" :controls="false" class="wide-number-input"></el-input-number>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="单价">
                            <el-input-number v-model="transEditDialog.form.price" :precision="4" :controls="false" class="wide-number-input"></el-input-number>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="手续费">
                            <el-input-number v-model="transEditDialog.form.fee" :precision="2" :controls="false" class="wide-number-input"></el-input-number>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="金额">
                            <el-input-number v-model="transEditDialog.form.amount" :precision="2" :controls="false" class="wide-number-input"></el-input-number>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-form-item label="备注">
                    <el-input v-model="transEditDialog.form.remark" type="textarea" :rows="2"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="transEditDialog.visible = false">取消</el-button>
                <el-button type="primary" @click="saveTransactionEdit">确定</el-button>
            
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
        </el-dialog>

        <!-- 证券资金流水编辑弹窗 -->
        <el-dialog v-model="cashFlowEditDialog.visible" title="编辑资金流水" width="520px">
            <el-form :model="cashFlowEditDialog.form" label-width="90px">
                <el-form-item label="日期">
                    <el-date-picker v-model="cashFlowEditDialog.form.date" type="date" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
                </el-form-item>
                <el-form-item label="证券账户">
                    <el-select v-model="cashFlowEditDialog.form.account" style="width: 100%">
                        <el-option v-for="acc in feeAccounts" :key="acc" :label="acc" :value="acc"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="类型">
                    <el-select v-model="cashFlowEditDialog.form.flow_type" style="width: 100%">
                        <el-option label="银证转入" value="银证转入"></el-option>
                        <el-option label="银证转出" value="银证转出"></el-option>
                        <el-option label="现金校准" value="现金校准"></el-option>
                        <el-option label="其他调整" value="其他调整"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="金额">
                    <el-input-number v-model="cashFlowEditDialog.form.amount" :precision="2" :controls="false" class="wide-number-input"></el-input-number>
                </el-form-item>
                <el-form-item label="备注">
                    <el-input v-model="cashFlowEditDialog.form.remark"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="cashFlowEditDialog.visible = false">取消</el-button>
                <el-button type="primary" @click="saveCashFlowEdit">保存</el-button>
            
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
        </el-dialog>

        <!-- 持仓强制校正弹窗 -->
        <el-dialog v-model="holdingCorrectionDialog.visible" title="持仓强制校正" width="620px">
            <el-alert
                title="校正会作为新的持仓锚点：校正日及之前交易不再追溯，校正日之后交易继续滚动计算。历史交易不会被修改。"
                type="warning"
                show-icon
                :closable="false"
                style="margin-bottom: 14px;"
            ></el-alert>
            <el-form :model="holdingCorrectionDialog.form" label-width="120px">
                <el-form-item label="标的">
                    <span>{{ holdingCorrectionDialog.form.name }} ({{ holdingCorrectionDialog.form.code }})</span>
                </el-form-item>
                <el-form-item label="校正日期">
                    <el-date-picker v-model="holdingCorrectionDialog.form.date" type="date" value-format="YYYY-MM-DD" style="width: 100%"></el-date-picker>
                </el-form-item>
                <el-row :gutter="16">
                    <el-col :span="12">
                        <el-form-item label="券商实际数量">
                            <el-input-number v-model="holdingCorrectionDialog.form.actual_quantity" :precision="2" :controls="false" class="wide-number-input"></el-input-number>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="普通成本价">
                            <el-input-number v-model="holdingCorrectionDialog.form.actual_avg_cost" :precision="6" :controls="false" class="wide-number-input"></el-input-number>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-form-item label="累计分红">
                    <el-input-number v-model="holdingCorrectionDialog.form.actual_total_dividend" :precision="2" :controls="false" class="wide-number-input"></el-input-number>
                </el-form-item>
                <el-form-item label="备注">
                    <el-input v-model="holdingCorrectionDialog.form.remark" placeholder="例如：按华泰持仓页强制校正"></el-input>
                </el-form-item>
                <el-form-item label="当前系统值">
                    <span style="color:#909399;">
                        数量 {{ holdingCorrectionDialog.current.quantity }}，普通成本 {{ formatMoney(holdingCorrectionDialog.current.avg_cost, 4) }}，摊薄成本 {{ formatMoney(holdingCorrectionDialog.current.diluted_cost, 4) }}，累计分红 {{ formatMoney(holdingCorrectionDialog.current.total_dividend || 0) }}
                    </span>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="holdingCorrectionDialog.visible = false">取消</el-button>
                <el-button type="primary" @click="saveHoldingCorrection">保存校正</el-button>
            
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
        </el-dialog>

        <!-- 持仓校正记录弹窗 -->
        <el-dialog v-model="holdingCorrectionHistoryDialog.visible" :title="holdingCorrectionHistoryDialog.title" width="760px">
            <el-table :data="holdingCorrectionHistoryDialog.records" stripe style="width:100%;">
                <el-table-column prop="date" label="日期" width="105" align="center"></el-table-column>
                <el-table-column label="数量" width="115" align="right" header-align="right">
                    <template #default="scope">{{ Number(scope.row.actual_quantity || 0).toLocaleString() }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column label="普通成本" width="115" align="right" header-align="right">
                    <template #default="scope">{{ formatMoney(scope.row.actual_avg_cost, 4) }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column label="累计分红" width="115" align="right" header-align="right">
                    <template #default="scope">{{ formatMoney(scope.row.actual_total_dividend || 0) }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip></el-table-column>
                <el-table-column label="操作" width="80" align="center">
                    <template #default="scope">
                        <el-button type="danger" link @click="deleteHoldingCorrection(scope.row)">删除</el-button>
                    
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
            </el-table>
            <template #footer>
                <el-button @click="holdingCorrectionHistoryDialog.visible = false">关闭</el-button>
            
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
        </el-dialog>

        <!-- 预计年化收益编辑弹窗 -->
        <el-dialog v-model="expectedReturnDialog.visible" title="编辑预计年化收益" width="400px">
            <el-form :model="expectedReturnDialog.form" label-width="100px">
                <el-form-item label="标的名称">
                    <span>{{ expectedReturnDialog.form.name }} ({{ expectedReturnDialog.form.code }})</span>
                </el-form-item>
                <el-form-item label="预计年化收益(%)">
                    <el-input-number v-model="expectedReturnDialog.form.expected_return" :precision="1" :min="0" :max="100" style="width: 100%"></el-input-number>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="expectedReturnDialog.visible = false">取消</el-button>
                <el-button type="primary" @click="saveExpectedReturn">确定</el-button>
            
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
        </el-dialog>


        <!-- 半自动分红草稿 -->
        <el-dialog v-model="dividendDialog.visible" title="半自动分红草稿" width="1080px" top="5vh">
            <el-alert
                title="支持 A 股个股 + 场内 ETF/港股ETF/REIT 现金分红草稿。按权益登记日持仓估算金额，并自动识别已有分红/分红再投资流水避免重复。开放式债基等仍需手工录入（交易管理里录「分红」）；金额为税前估算，确认前请对照券商到账。"
                type="info"
                show-icon
                :closable="false"
                style="margin-bottom: 12px;"
            ></el-alert>
            <el-alert
                v-if="(dividendDialog.unsupported || []).length"
                :title="`当前有 有 ${dividendDialog.unsupported.length} 只持仓不支持自动扫描（常见：开放式债基、场外基金）。请下载分红模板手工补录后导入，或在「交易记录」新增方向选「分红」录入。`"
                type="warning"
                show-icon
                :closable="false"
                style="margin-bottom: 12px;"
            ></el-alert>
            <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px;align-items:center;">
                <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                    <span style="color:#606266;">回看天数</span>
                    <el-input-number v-model="dividendDialog.lookbackDays" :min="30" :max="2000" :step="30"></el-input-number>
                    <el-button type="primary" :loading="dividendLoading" @click="scanDividendDrafts">扫描分红</el-button>
                    <el-button @click="selectSelectableDividendDrafts">全选可确认</el-button>
                    <el-button @click="clearDividendDraftSelection">清空选择</el-button>
                </div>
                <div style="color:#909399;font-size:13px;" v-if="dividendDialog.summary">
                    新草稿 {{ dividendDialog.summary.new_count || 0 }} /
                    已有流水 {{ dividendDialog.summary.already_recorded_count || 0 }} /
                    零持仓 {{ dividendDialog.summary.zero_qty_count || 0 }} /
                    不支持 {{ dividendDialog.summary.unsupported_holdings || 0 }}
                </div>
            </div>
            <el-table
                ref="dividendTableRef"
                :data="dividendDialog.drafts"
                stripe
                max-height="480"
                style="width:100%;"
                @selection-change="onDividendSelectionChange"
                empty-text="暂无草稿，请先扫描"
            >
                <el-table-column type="selection" width="48" :selectable="isDividendDraftSelectable"></el-table-column>
                <el-table-column label="状态" width="110" align="center">
                    <template #default="scope">
                        <el-tag :type="dividendStatusType(scope.row.status)" size="small">{{ dividendStatusLabel(scope.row.status) }}</el-tag>
                    
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column prop="event_date" label="除权/事件日" width="115" align="center"></el-table-column>
                <el-table-column label="标的" min-width="150">
                    <template #default="scope">
                        <div>{{ scope.row.name }}</div>
                        <div style="color:#909399;font-size:12px;">{{ scope.row.code }} · {{ scope.row.category || '未分类' }}</div>
                    
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column prop="plan_profile" label="方案" min-width="150" show-overflow-tooltip></el-table-column>
                <el-table-column label="登记日数量" width="110" align="right">
                    <template #default="scope">{{ Number(scope.row.quantity_on_record_date || 0).toLocaleString() }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column label="每股分红" width="95" align="right">
                    <template #default="scope">{{ formatMoney(scope.row.cash_per_share, 4) }}
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column label="估算金额" width="120" align="right">
                    <template #default="scope">
                        <el-input-number
                            v-if="scope.row.selectable"
                            v-model="scope.row.amount"
                            :precision="2"
                            :controls="false"
                            class="wide-number-input"
                            style="width:110px;"
                        ></el-input-number>
                        <span v-else>{{ formatMoney(scope.row.amount) }}</span>
                    
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
                <el-table-column label="匹配/说明" min-width="180" show-overflow-tooltip>
                    <template #default="scope">
                        <span style="color:#909399;font-size:12px;">{{ scope.row.reason || scope.row.assign_progress || '' }}</span>
                    
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
                </el-table-column>
            </el-table>
            <template #footer>
                <div style="display:flex;justify-content:space-between;align-items:center;width:100%;gap:12px;flex-wrap:wrap;">
                    <span style="color:#909399;font-size:13px;">已选 {{ dividendDialog.selected.length }} 条，确认后写入「分红」交易并重算持仓/现金</span>
                    <div>
                        <el-button size="small" @click="downloadDividendTemplate">下载分红模板</el-button>
                        <el-upload action="#" :auto-upload="false" :show-file-list="false" accept=".csv" :on-change="importDividends" style="display:inline-block;margin-right:8px;">
                            <el-button size="small" type="success">导入分红CSV</el-button>
                        </el-upload>
                        <el-button @click="dividendDialog.visible = false">关闭</el-button>
                        <el-button type="primary" :loading="dividendConfirming" @click="confirmSelectedDividends">确认入账</el-button>
                    </div>
                </div>
            
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
        </el-dialog>

        <!-- 晚间简报 -->
        <el-dialog v-model="eveningBriefDialog.visible" title="晚间简报" width="560px">
            <pre style="white-space:pre-wrap;font-family:inherit;font-size:13px;line-height:1.6;margin:0;color:#303133;">{{ eveningBriefDialog.text || '（空）' }}</pre>
            <template #footer>
                <el-button @click="eveningBriefDialog.visible = false">关闭</el-button>
                <el-button type="primary" plain :loading="eveningBriefDialog.loading" @click="openEveningBrief(true)">推送通知</el-button>
            
        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>
        </el-dialog>

        <!-- UZI-Skill 混合分析提示（复制到本地 Hermes 执行） -->
        <el-dialog v-model="uziAnalysisDialog.visible" title="UZI 深度分析提示" width="820px" top="8vh">
            <div v-if="uziAnalysisDialog.row">
                <div style="margin-bottom:8px; color:#606266;">
                    {{ uziAnalysisDialog.row.name }} ({{ uziAnalysisDialog.row.code }})
                    <span style="margin-left:12px;">当前深度：</span>
                    <el-radio-group v-model="uziAnalysisDialog.depth" @change="updateUziDepth" size="small" style="margin-left:6px;">
                        <el-radio-button label="lite">lite</el-radio-button>
                        <el-radio-button label="medium">medium（推荐）</el-radio-button>
                        <el-radio-button label="deep">deep</el-radio-button>
                    </el-radio-group>
                </div>

                <el-alert
                    title="此为混合模式：点击下方按钮复制提示词后，在你本机的 Hermes 中直接粘贴执行 UZI-Skill。"
                    type="info"
                    :closable="false"
                    style="margin-bottom:10px;"
                />

                <el-input
                    type="textarea"
                    v-model="uziAnalysisDialog.prompt"
                    :rows="12"
                    readonly
                    style="font-family: monospace; font-size: 13px;"
                />

                <div style="margin-top:8px; font-size:12px; color:#909399;">
                    提示：推荐先用 medium，复杂标的再用 deep。执行后把生成的 HTML 报告保存即可。
                </div>
            </div>

            <template #footer>
                <el-button @click="closeUziAnalysisDialog">关闭</el-button>
                <el-button type="primary" @click="copyUziPrompt">复制提示词</el-button>
            </template>
        </el-dialog>

</template>

<script setup>
import { useAppCtx } from '../composables/useAppCtx.js';
const { dividendLoading, dividendConfirming, dividendDialog, dividendTableRef, feeAccounts, depositDialog, cashFlowEditDialog, transDialog, expectedReturnDialog, holdingCorrectionDialog, holdingCorrectionHistoryDialog, transEditDialog, eveningBriefDialog, openEveningBrief, scanDividendDrafts, confirmSelectedDividends, selectSelectableDividendDrafts, clearDividendDraftSelection, onDividendSelectionChange, isDividendDraftSelectable, dividendStatusLabel, dividendStatusType, saveDeposit, saveCashFlowEdit, saveTransactionEdit, saveExpectedReturn, saveHoldingCorrection, deleteHoldingCorrection, uziAnalysisDialog, updateUziDepth, copyUziPrompt, closeUziAnalysisDialog, formatMoney, downloadDividendTemplate, importDividends } = useAppCtx();
</script>
