window.HMTSTC_APP_INTELLIGENCE = {
  acceptStrategyDraft: async function () {
    const draft = (((HMTSTC_DATA.intelligence || {}).model_intelligence || {}).strategy_generator || {}).drafts || [];
    const first = draft[0] || {};
    const draftId = first.id || 'AUTO_DRAFT_SCALP_001';
    const ok = this.confirmAction ? await this.confirmAction({ title: 'Strateji Taslağı', message: draftId + ' paper-only izleme listesine alınsın mı?', level: 'warn' }) : confirm(draftId + ' izlemeye alınsın mı?');
    if (!ok) return;
    try {
      await this.fetchJson('/api/intelligence/strategy-generator/accept-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft_id: draftId })
      });
      await this.auditAction('strategy_generator_accept', 'ok', draftId, { draft_id: draftId });
      await this.syncApiData();
    } catch (error) {
      alert(this.apiErrorMessage(error, 'Strateji taslağı izlemeye alınamadı.'));
    }
  }
};
