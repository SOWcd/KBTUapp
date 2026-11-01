<script lang="ts">
  // Admin → Badges (owner, Nov 2): a badge's variant by hand (the initiation's guest, volunteer, performer). Pick the
  // variant, find a student by name, @username or ID, give with a confirm; take back with a confirm and an undo. Both
  // audited on the server; the student gets the usual unlock moment and the bot's card. The owner also gives a variant
  // to everyone counted at a check-in session (it was on /show's sheet: staff controls live here only).
  import Medal from '@lucide/svelte/icons/medal';
  import { api, type BadgeHolder, type BadgeSession } from '../../lib/api';
  import { BADGES, variantName } from '../../lib/awards';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, shareCard } from '../../lib/tg';
  import Send from '@lucide/svelte/icons/send';
  import Button from '../../ui/Button.svelte';
  import { dayMonth } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import SearchField from '../../ui/SearchField.svelte';

  let { overlay }: { overlay: Overlay } = $props();

  let badge = $state(BADGES[0].code), code = $state(BADGES[0].variants[0].code);
  const vname = (c: string) => variantName(badge, c);
  const emojiOf = (c: string) => BADGES.flatMap((b) => b.variants).find((v) => v.code === c)?.emoji ?? '';

  // the search: as typed, the last answer wins
  let q = $state(''), found = $state<BadgeHolder[] | null>(null), asked = 0;
  $effect(() => {
    const s = q.trim();
    if (s.length < 2 && !/^\d+$/.test(s)) { found = null; return; }
    const n = ++asked;
    const id = setTimeout(() => api.badgePeople(s).then((r) => { if (n === asked) found = r; }).catch(() => { if (n === asked) found = []; }), 250);
    return () => clearTimeout(id);
  });

  // the last change, undoable from its row until the next one
  let last = $state<{ id: number; code: string; on: boolean } | null>(null);
  function put(p: BadgeHolder, c: string, on: boolean, undo = false) {
    const was = p.has;
    p.has = on ? [...was, c] : was.filter((x) => x !== c); // the row answers in the same frame
    last = undo ? null : { id: p.person.id, code: c, on };
    api.badgeSet(p.person.id, c, on).then((r) => { p.has = r.has; haptic.ok(); if (!undo) say(t(on ? 'bdg.given' : 'bdg.taken'), on ? 'party_popper_3d' : 'waving_hand_3d_default'); })
      .catch(() => { p.has = was; last = null; haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
  async function give(p: BadgeHolder) {
    if (await sheets.ask({ title: t('bdg.giveAsk', { variant: vname(code), name: p.person.name }), text: t('bdg.giveText'), ok: t('bdg.give'), cancel: t('common.cancel') })) put(p, code, true);
  }
  async function take(p: BadgeHolder) {
    if (await sheets.ask({ title: t('bdg.takeAsk', { variant: vname(code), name: p.person.name }), ok: t('bdg.take'), cancel: t('common.cancel'), danger: true })) put(p, code, false);
  }

  // a one-time link for the picked variant, sent from my Telegram: the bot's card with "Get it" (logic.grant_link)
  let sending = $state(false);
  async function sendLink() {
    sending = true; haptic.tap();
    const award = `${t(`ach.${badge}.name` as 'ach.init26.name')} · ${vname(code)}`;
    try { if (await shareCard({ kind: 'gl', id: '0', code }, 'https://t.me/KBTUappBot', award)) { haptic.ok(); say(t('give.sent'), 'party_popper_3d'); } }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { sending = false; }
  }

  // the owner's batch grant
  const owner = $derived(session.me?.role === 'admin' && !!session.me?.founder);
  let sessions = $state<BadgeSession[]>([]);
  $effect(() => { if (owner) api.badgeSessions().then((l) => (sessions = l)).catch(() => {}); });
  async function grantAll(s: BadgeSession) {
    if (!(await sheets.ask({ title: t('scr.grantAsk', { variant: vname(code) }), text: t('scr.grantText', { n: s.done }), ok: t('scr.grant'), cancel: t('scr.keep') }))) return;
    try { const r = await api.screenGrant(s.id, code); haptic.ok(); say(t('scr.granted', { n: r.granted }), 'party_popper_3d'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<Sheet {overlay} full title={t('bdg.title')} icon={Medal}>
  {#each BADGES as b (b.code)}
    <h3 class="t-cap sh">{t(`ach.${b.code}.name` as 'ach.init26.name')}</h3>
    <div class="vars" role="radiogroup">
      {#each b.variants as v (v.code)}
        <button class="var surface" role="radio" aria-checked={code === v.code} class:on={code === v.code}
          onclick={() => { haptic.select(); badge = b.code; code = v.code; last = null; }}>
          <img src={`emoji/${v.emoji}.webp`} alt="" draggable="false" />
          <span>{variantName(b.code, v.code)}</span>
        </button>
      {/each}
    </div>
  {/each}

  <div class="link"><Button kind="primary" size="m" full loading={sending} onclick={sendLink}>{#snippet icon()}<Send size={17} />{/snippet}{t('bdg.link')}</Button></div>
  <p class="t-foot note">{t('bdg.linkNote')}</p>

  <div class="find"><SearchField bind:value={q} placeholder={t('bdg.find')} /></div>
  {#if found && !found.length}<p class="t-foot none">{t('bdg.none')}</p>{/if}
  {#if found?.length}
    <div class="rows surface">
      {#each found as p (p.person.id)}
        {@const has = p.has.includes(code)}
        <div class="pr">
          <button class="who" onclick={() => sheets.person(p.person.id)}>
            <Avatar person={p.person} size={40} tappable={false} />
            <span class="tx"><b class="ellipsis">{p.person.name}</b><i class="ellipsis">{p.username ? '@' + p.username : ''}</i></span>
            {#each p.has as h (h)}{#if emojiOf(h)}<img class="held" src={`emoji/${emojiOf(h)}.webp`} alt={vname(h)} title={vname(h)} />{/if}{/each}
          </button>
          {#if last && last.id === p.person.id && last.code === code}
            <button class="act" onclick={() => put(p, code, !last!.on, true)}>{t('bdg.undo')}</button>
          {:else if has}
            <button class="act bad" onclick={() => take(p)}>{t('bdg.take')}</button>
          {:else}
            <button class="act" onclick={() => give(p)}>{t('bdg.give')}</button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  {#if owner && sessions.length}
    <h3 class="t-cap sh">{t('bdg.sessions')}</h3>
    <div class="rows surface">
      {#each sessions as s (s.id)}
        <div class="pr">
          <span class="tx sess"><b class="ellipsis">{s.title}</b><i class="ellipsis">{dayMonth(s.at)} · {t('bdg.counted', { n: s.done })}</i></span>
          <button class="act" disabled={!s.done} onclick={() => grantAll(s)}>{t('bdg.give')}</button>
        </div>
      {/each}
    </div>
  {/if}
</Sheet>

<style>
  .sh { margin: 4px 2px 8px; }
  .sh:not(:first-child) { margin-top: 22px; }
  .vars { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .var { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px 6px 10px; min-width: 0;
    font: 620 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); transition: box-shadow .15s; }
  .var img { width: 60px; height: 60px; object-fit: contain; opacity: 0.55; filter: grayscale(0.5); transition: opacity .15s, filter .15s; }
  .var span { max-width: 100%; text-align: center; hyphens: manual; }
  .var.on { box-shadow: 0 0 0 2px var(--accent); color: var(--text); }
  .var.on img { opacity: 1; filter: drop-shadow(0 3px 6px rgba(0, 0, 0, 0.35)); }
  .var:active { transform: scale(0.97); }
  .link { margin-top: 12px; }
  .note { margin: 8px 4px 0; }
  .find { margin-top: 18px; }
  .none { margin: 12px 4px 0; }
  .rows { display: flex; flex-direction: column; margin-top: 10px; padding: 4px 0; }
  .pr { display: flex; align-items: center; gap: 8px; padding-right: 12px; min-width: 0; }
  .pr + .pr { border-top: 1px solid var(--line); }
  .who { flex: 1; min-width: 0; display: flex; align-items: center; gap: 12px; padding: 10px 0 10px 14px; text-align: left; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx.sess { padding: 10px 0 10px 14px; }
  .tx b { font: 650 var(--fs-body)/1.25 var(--font-text); }
  .tx i { font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .held { flex: none; width: 22px; height: 22px; object-fit: contain; }
  .act { flex: none; height: 32px; padding: 0 14px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 var(--fs-sub)/1 var(--font-text); }
  .act.bad { background: var(--danger-soft); color: var(--danger-text); }
  .act:disabled { opacity: 0.45; }
</style>
