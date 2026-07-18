import { normalizeText, inferCategoryByCode } from '../utils/index.js';

/**
 * Asset suggestion helpers for transaction form autocompletion.
 * Extracted from main.js.
 */
export function createAssetHelpers({ holdings, transForm }) {
    const assetOptions = () => (holdings.value || []).map(h => ({
        value: `${h.code} ${h.name} ${h.category || ''}`,
        code: h.code,
        name: h.name,
        category: h.category || '',
        label: `${h.code} - ${h.name} - ${h.category || '未分类'}`,
    }));

    const queryAssetByCode = (queryString, cb) => {
        const q = normalizeText(queryString);
        const results = assetOptions()
            .filter(a => !q || normalizeText(a.code).includes(q) || normalizeText(a.name).includes(q))
            .map(a => ({ ...a, value: a.code, label: a.label }));
        cb(results);
    };

    const queryAssetByName = (queryString, cb) => {
        const q = normalizeText(queryString);
        const results = assetOptions()
            .filter(a => !q || normalizeText(a.name).includes(q) || normalizeText(a.code).includes(q))
            .map(a => ({ ...a, value: a.name, label: a.label }));
        cb(results);
    };

    const selectTransAsset = (asset) => {
        if (!transForm || !asset) return;
        transForm.value.code = asset.code;
        transForm.value.name = asset.name;
        transForm.value.category = asset.category || '';
    };

    const autoMatchTransAsset = (field, rawValue = null) => {
        if (!transForm) return;
        const codeQ = normalizeText(field === 'code' && rawValue !== null ? rawValue : transForm.value.code);
        const nameQ = normalizeText(field === 'name' && rawValue !== null ? rawValue : transForm.value.name);

        if (!codeQ && !nameQ) {
            transForm.value.category = '';
            return;
        }

        let match = null;
        if (field === 'code' && codeQ) {
            match = (holdings.value || []).find(h => normalizeText(h.code) === codeQ);
        } else if (field === 'name' && nameQ) {
            match = (holdings.value || []).find(h => normalizeText(h.name) === nameQ);
            if (!match) {
                const candidates = (holdings.value || []).filter(h => normalizeText(h.name).includes(nameQ));
                if (candidates.length === 1) match = candidates[0];
            }
        }

        if (match) {
            transForm.value.code = match.code;
            transForm.value.name = match.name;
            transForm.value.category = match.category || inferCategoryByCode(match.code, match.name);
        } else {
            transForm.value.category = inferCategoryByCode(transForm.value.code, transForm.value.name);
        }
    };

    return {
        queryAssetByCode,
        queryAssetByName,
        selectTransAsset,
        autoMatchTransAsset,
    };
}
