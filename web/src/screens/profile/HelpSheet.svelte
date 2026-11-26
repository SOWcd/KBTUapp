<script lang="ts">
  // "Help the app": students make it, and here is how to join in. The ways out (the donate page, the bugs-and-ideas
  // group, the code, what is wrong, the people already named), then a short signed offer the creator reads in Admin
  // (server logic/helpus.py; the line under the form is its own consent, sent as CONSENT).
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import MessageCircleWarning from '@lucide/svelte/icons/message-circle-warning';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import { CODE, TALK } from '../../lib/feedback';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const KINDS = ['code', 'design', 'ideas', 'partner', 'lang', 'test'] as const;
  const CONSENT = '2026-11-24'; // server helpus.CONSENT: the wording of help.consent
  let picked = $state<string[]>([]);
  let note = $state('');
  let busy = $state(false);
  const flip = (k: string) => { haptic.select(); picked = picked.includes(k) ? picked.filter((x) => x !== k) : [...picked, k]; };
  const go = (url: string) => { haptic.tap(); openLink(url); };
  async function send() {
    if (busy || !picked.length) return;
    busy = true;
    try {
      await api.helpOffer(picked, note.trim(), CONSENT);
      haptic.ok(); count('do.helpus'); say(t('help.sent'), 'raising_hands_3d_default'); close(overlay.id);
    } catch (e) {
      haptic.error(); say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'fb.many' : 'common.error'), 'warning_3d');
    }
    busy = false;
  }
</script>

<Sheet {overlay} icon={HeartHandshake} title={t('help.title')}>
  <div class="help">
    <p class="t-body dim">{t('help.text')}</p>
    <Group footnote={t('help.credit')}>
      {#if session.donate}<Row icon={HandHeart} title={t('set.donate')} tone="action" accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('donate'); }} />{/if}
      <Row icon={MessagesSquare} title={t('help.bug')} value={t('app.group').toLowerCase()} accessory="external" onclick={() => go(TALK)} />
      <Row icon={MessageCircleWarning} title={t('fb.title')} accessory="chevron" onclick={() => { haptic.tap(); sheets.feedback(); }} />
      <Row icon={GitHubMark} title={t('help.code')} value="GitHub" accessory="external" onclick={() => go(`${CODE}/blob/main/CONTRIBUTING.md`)} />
      <Row icon={UsersRound} title={t('cr.title')} accessory="chevron" onclick={() => { haptic.tap(); sheets.credits(); }} />
    </Group>
    <h3 class="t-h3 cap">{t('help.formT')}</h3>
    <div class="chips">{#each KINDS as k (k)}<Chip selected={picked.includes(k)} onclick={() => flip(k)}>{t(`help.k.${k}`)}</Chip>{/each}</div>
    <Field label={t('help.note')} bind:value={note} multiline rows={2} maxlength={500} />
    <p class="t-foot dim">{t('help.consent')}</p>
  </div>

  {#snippet footer()}
    <Button kind="primary" size="l" full disabled={!picked.length} loading={busy} onclick={send}>{t('help.send')}</Button>
  {/snippet}
</Sheet>

<style>
  .help { display: flex; flex-direction: column; gap: var(--s-4); padding: var(--s-2) 0; }
  .dim { margin: 0; color: var(--text-2); text-wrap: pretty; }
  .cap { margin: var(--s-2) 0 0; }
  .chips { display: flex; flex-wrap: wrap; gap: var(--s-2); }
</style>
