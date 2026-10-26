<script lang="ts">
  // Admin → the audit log: the owner reads everything done with power, the last 200: who, what, to whom.
  import ScrollText from '@lucide/svelte/icons/scroll-text';
  import { api, type AuditRow } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let log = $state<AuditRow[] | null>(null);
  $effect(() => { api.audit().then((l) => (log = l)).catch(() => { log = []; say(t('common.error'), 'pleading_face_3d'); }); });

  const KNOWN = ['staff_role', 'ban', 'unban', 'report_remove', 'report_keep', 'restore', 'post_hide', 'feature', 'grant', 'ungrant',
    'official', 'org_create', 'org_edit', 'org_hide', 'role_change', 'presidency_transfer', 'president_handover', 'president_link',
    'receipt_reject', 'registry_search', 'registry_roster', 'registry_export', 'attendees_export', 'delete_my_data', 'first50',
    'link_create', 'link_delete', 'link_revoke'] as const;
  const label = (a: string) => ((KNOWN as readonly string[]).includes(a) ? t(`audit.a.${a as (typeof KNOWN)[number]}`) : a);
  // the few details worth a line: a role's change, a ban's reason
  const detail = (r: AuditRow) => {
    const d = r.data as Record<string, string>;
    if (r.action === 'staff_role' && d.to) return `${t(`staff.role.${d.from as 'user'}`)} → ${t(`staff.role.${d.to as 'user'}`)}`;
    if (r.action === 'ban' && d.reason) return d.reason;
    if (r.action.startsWith('link_')) return `/${d.slug}`;
    return '';
  };
</script>

<Sheet {overlay} full title={t('audit.title')} icon={ScrollText}>
  {#if log && !log.length}<p class="t-callout dim">{t('audit.empty')}</p>{/if}
  {#if log?.length}
    <div class="rows surface">
      {#each log as r (r.id)}
        <div class="ar">
          {#if r.actor}<Avatar person={r.actor} size={32} tappable={false} />{:else}<span class="sys">⚙︎</span>{/if}
          <span class="tx">
            <b>{r.actor?.name ?? t('audit.system')} · {label(r.action)}</b>
            <i class="selectable">{[r.targetName ?? r.target, detail(r)].filter(Boolean).join(' · ')}</i>
          </span>
          <time class="num">{ago(r.at)}</time>
        </div>
      {/each}
    </div>
  {/if}
</Sheet>

<style>
  .dim { color: var(--text-2); }
  .rows { display: flex; flex-direction: column; padding: 4px 0; }
  .ar { display: flex; align-items: center; gap: 10px; padding: 10px 14px; }
  .ar + .ar { border-top: 1px solid var(--line); }
  .sys { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-2); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 620 14px/1.3 var(--font-text); }
  .tx i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); overflow-wrap: anywhere; }
  time { flex: none; font: 550 12.5px/1 var(--font-text); color: var(--text-2); }
</style>
