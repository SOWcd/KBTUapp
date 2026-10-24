<script lang="ts">
  // The week's memo to DMP (PLAN stage 2, their rules: Wednesdays 9:00-18:00, one email for the week, from the KBTU
  // address to youth_policy@kbtu.kz). The server writes one memo from the events' requests in DMP's form, signed by me in kk, ru,
  // en; here it can be fixed by hand, then the Outlook app opens with it through public/outlook.html (a Mini App can't open
  // mailto: or ms-outlook: itself, Telegram's openLink takes http/https only), or it's copied. Back in the app it asks "Sent it?": the events sent
  // leave the next memos and the others see who sent it. Opened from Studio and the bot's Wednesday message.
  import Copy from '@lucide/svelte/icons/copy';
  import Mail from '@lucide/svelte/icons/mail';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Plus from '@lucide/svelte/icons/plus';
  import { onMount } from 'svelte';
  import { api, type Id, type MemoDraft, type MemoSign } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth, nowTs, relDay, time } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  let draft = $state<MemoDraft | null>(null);
  let text = $state('');
  let printText = $state(''); // the Publishing Center's own letter (ic@kbtu.kz): printing is not DMP's (owner, Oct 14)
  let later = $state(false);
  let signing = $state<MemoSign | null>(null);
  let opened = false; // I opened Outlook or copied: back in the app, ask whether it went
  const oops = () => { haptic.error(); say(t('common.error'), 'pleading_face_3d'); };
  const load = () => api.memo(org, later).then((d) => { draft = d; text = d.text; printText = d.print?.text ?? ''; }).catch(oops);
  $effect(() => { load(); });

  onMount(() => {
    const back = async () => {
      if (document.visibilityState !== 'visible' || !opened || !draft?.events.length) return;
      opened = false;
      if (!(await sheets.ask({ title: t('memo.sentAsk'), ok: t('memo.sentYes'), cancel: t('memo.sentNo') }))) return;
      try { await api.memoSent(org, draft.events.map((e) => e.id)); haptic.ok(); say(t('memo.sentDone'), 'sparkles_3d'); load(); }
      catch { oops(); }
    };
    document.addEventListener('visibilitychange', back);
    return () => document.removeEventListener('visibilitychange', back);
  });

  function mark() { opened = true; api.memoOpened(org).catch(() => {}); }
  // our page opens the Outlook app (the web compose in Telegram's browser is signed out); the letter rides in the #fragment
  function outlook(to: string, subject: string, body: string) {
    haptic.tap();
    const q = (s: string) => encodeURIComponent(s);
    openLink(`${location.origin}/outlook.html#to=${q(to)}&subject=${q(subject)}&body=${q(body)}&b=${q(t('memo.outlook'))}&w=${q(t('memo.web'))}`);
  }
  async function copy(body: string) {
    try { await navigator.clipboard.writeText(body); haptic.ok(); say(t('memo.copied'), 'sparkles_3d'); return true; }
    catch { haptic.error(); return false; }
  }
  // only DMP's letter asks "Sent it?" on the way back
  function toDmp() { if (draft) { mark(); outlook(draft.to, draft.subject, text); } }
  async function copyDmp() { if (await copy(text)) mark(); }
  async function again(id: Id) {
    try { await api.memoAgain(org, id); haptic.soft(); load(); } catch { oops(); }
  }
  async function saveSign() {
    if (!signing) return;
    try { await api.memoSign(org, signing); signing = null; haptic.ok(); say(phrase('say.signSaved'), 'love_letter_3d'); load(); } catch { oops(); }
  }
  const ITEMS = ['room', 'guests', 'provide', 'promo', 'gear', 'film'] as const; // printing has its own letter
  let area = $state<HTMLTextAreaElement>();
  // the next number before the signature; an empty item leaves the cursor after "N) " to type it
  // ponytail: numbers by the largest "N) " in the text, a long equipment list inside an item could outnumber the items
  function put(item: string) {
    if (!draft) return;
    const n = Math.max(0, ...[...text.matchAll(/^(\d+)\) /gm)].map((m) => +m[1])) + 1;
    const at = text.lastIndexOf(draft.signFrom);
    const head = (at < 0 ? text : text.slice(0, at)).trimEnd() + `\n${n}) `;
    text = head + item + '\n\n' + (at < 0 ? '' : text.slice(at));
    haptic.tap();
    if (!item) setTimeout(() => { area?.focus(); area?.setSelectionRange(head.length, head.length); }, 50);
  }
  const when = (ts: number) => `${relDay(ts)}, ${time(ts)}`;
</script>

<Sheet {overlay} full title={t('memo.title')}>
  <h2 class="t-h2">{t('memo.title')}</h2>
  {#if draft}
    <p class="t-foot sub">{t('memo.week', { from: dayMonth(draft.from), to: dayMonth(draft.until - 1) })}</p>
    <p class="rules">{t('memo.rules')}</p>
    {#if draft.opened && draft.opened.at > nowTs() - 7 * 86400}
      <p class="t-foot state">{t('memo.openedBy', { name: draft.opened.by ?? '—', when: when(draft.opened.at) })}</p>
    {/if}
    {#if draft.later.length || later}
      <label class="switch"><span><b>{t('memo.later')}</b><i class="t-foot">{t('memo.laterHint', { n: draft.later.length })}</i></span>
        <input type="checkbox" role="switch" bind:checked={later} onchange={load} /></label>
    {/if}
    {#if draft.text}
      <!-- items without an event (owner, Oct 15): a small form writes the paragraph, it goes in before the signature -->
      <h3 class="t-cap sec">{t('memo.add')}</h3>
      <div class="chips">
        {#each ITEMS as k (k)}<button class="chip" onclick={() => sheets.memoItem(org, k, draft!.from, put)}><Plus size={15} />{t(`memo.${k}`)}</button>{/each}
        <button class="chip" onclick={() => put('')}><Plus size={15} />{t('memo.ownItem')}</button>
      </div>
      <label class="field body"><textarea bind:this={area} bind:value={text} rows="16" spellcheck="false"></textarea></label>
      {#if draft.guests}<p class="t-foot note">{t('memo.speakers')}</p>{/if}
    {/if}
    {#if draft.print}
      {@const pr = draft.print}
      <h3 class="t-cap sec">{t('memo.printTitle')}</h3>
      <p class="t-foot note top">{t('memo.attach')}</p>
      <label class="field"><textarea bind:value={printText} rows="10" spellcheck="false"></textarea></label>
      <div class="pair">
        <Button kind="secondary" size="m" full onclick={() => outlook(pr.to, pr.subject, printText)}>{#snippet icon()}<Mail size={17} />{/snippet}{t('memo.outlook')}</Button>
        <button class="copy" onclick={() => copy(printText)}><Copy size={16} />{t('memo.copy')}</button>
      </div>
    {/if}

    <!-- my signature: the Latin name and the positions, fixed once -->
    {#if signing}
      <div class="sign surface">
        <label class="field"><span class="t-cap">{t('memo.nameEn')}</span><input bind:value={signing.nameEn} maxlength="120" placeholder={draft.sign.nameEn} /></label>
        {#each ['kk', 'ru', 'en'] as const as l (l)}
          <label class="field"><span class="t-cap">{t(`memo.pos.${l}`)}</span><input bind:value={signing[l]} maxlength="120" placeholder={draft.sign[l]} /></label>
        {/each}
        <Button kind="primary" size="m" full onclick={saveSign}>{t('common.save')}</Button>
      </div>
    {:else}
      <button class="row surface me" onclick={() => (signing = { nameEn: draft!.sign.nameEn, kk: draft!.sign.kk, ru: draft!.sign.ru, en: draft!.sign.en })}>
        <span class="tx"><b class="ellipsis">{draft.sign.nameEn}</b><i class="ellipsis">{t('memo.sign')} · {draft.sign.ru}</i></span>
        <Pencil size={17} />
      </button>
    {/if}

    {#if draft.sent.length}
      <h3 class="t-cap sec">{t('memo.sent')}</h3>
      {#each draft.sent as e (e.id)}
        <div class="row surface">
          <span class="tx"><b class="ellipsis">{e.title}</b><i>{t('memo.sentBy', { name: e.sentBy ?? '—', when: when(e.sentAt ?? 0) })}</i></span>
          <button class="again" onclick={() => again(e.id)}>{t('memo.again')}</button>
        </div>
      {/each}
    {/if}
    {#if draft.without.length}
      <h3 class="t-cap sec">{t('memo.without')}</h3>
      {#each draft.without as e (e.id)}
        <button class="row surface" disabled={!draft.canEdit} onclick={() => sheets.editor(org, e.id)}>
          <span class="tx"><b class="ellipsis">{e.title}</b><i>{relDay(e.startsAt)}, {time(e.startsAt)}{e.draft ? ' · ' + t('memo.draft') : ''}</i></span>
          {#if draft.canEdit}<Pencil size={17} />{/if}
        </button>
      {/each}
    {/if}
  {/if}

  {#snippet footer()}
    {#if draft?.text}
      <Button kind="primary" size="l" full onclick={toDmp}>{#snippet icon()}<Mail size={18} />{/snippet}{t('memo.outlook')}</Button>
      <button class="copy" onclick={copyDmp}><Copy size={16} />{t('memo.copy')}</button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .sub { margin-top: 2px; }
  .rules { margin: 12px 0; padding: 12px 14px; border-radius: var(--r-m); background: var(--accent-soft); font: 550 14px/1.4 var(--font-text); }
  .state { margin: -4px 4px 12px; color: var(--accent-text); }
  .switch { margin-bottom: 12px; }
  .body textarea { min-height: 320px; font: 500 14px/1.45 var(--font-text); }
  .note { margin: 8px 4px 0; }
  .top { margin: -2px 4px 10px; }
  .pair { display: flex; flex-direction: column; align-items: stretch; margin-top: 10px; }
  .sign { display: flex; flex-direction: column; gap: 8px; padding: 12px; margin-top: 14px; }
  .sec { margin: 20px 2px 8px; }
  .row { display: flex; align-items: center; gap: 10px; width: 100%; padding: 12px 14px; margin-bottom: 8px; text-align: left; color: var(--text-3); }
  .me { margin-top: 14px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .chip { display: flex; align-items: center; gap: 5px; height: 34px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 620 14px/1 var(--font-text); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { color: var(--text); font: 620 15px/1.25 var(--font-text); }
  .tx i { font: 500 13px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  .again { flex: none; height: 30px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 620 13px/1 var(--font-text); }
  .copy { display: flex; align-items: center; justify-content: center; gap: 8px; margin: 12px auto 2px; padding: 6px 10px; font: 620 14px/1 var(--font-text); color: var(--text-2); }
</style>
