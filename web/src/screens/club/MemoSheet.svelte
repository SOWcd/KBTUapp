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
  import NotebookPen from '@lucide/svelte/icons/notebook-pen';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Notice from '../../ui/Notice.svelte';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  let draft = $state<MemoDraft | null>(null);
  let text = $state('');
  let printText = $state(''); // the Publishing Center's own letter (ic@kbtu.kz): printing is not DMP's
  let later = $state(false);
  let signing = $state<MemoSign | null>(null);
  let opened = false; // I opened Outlook or copied: back in the app, ask whether it went
  const oops = () => { haptic.error(); say(t('common.error'), 'warning_3d'); };
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
  // engine: Field could hand out its input (focus, the caret): found in its wrapper for now
  let areaBox = $state<HTMLElement>();
  // the next number before the signature; an empty item leaves the cursor after "N) " to type it
  // ponytail: numbers by the largest "N) " in the text, a long equipment list inside an item could outnumber the items
  function put(item: string) {
    if (!draft) return;
    const n = Math.max(0, ...[...text.matchAll(/^(\d+)\) /gm)].map((m) => +m[1])) + 1;
    const at = text.lastIndexOf(draft.signFrom);
    const head = (at < 0 ? text : text.slice(0, at)).trimEnd() + `\n${n}) `;
    text = head + item + '\n\n' + (at < 0 ? '' : text.slice(at));
    haptic.tap();
    if (!item) setTimeout(() => { const area = areaBox?.querySelector('textarea'); area?.focus(); area?.setSelectionRange(head.length, head.length); }, 50);
  }
  const when = (ts: number) => `${relDay(ts)}, ${time(ts)}`;
</script>

<Sheet {overlay} icon={NotebookPen} full title={t('memo.title')}>
  {#if draft}
    <div class="stack">
      <p class="hint">{t('memo.week', { from: dayMonth(draft.from), to: dayMonth(draft.until - 1) })}</p>
      <Notice text={t('memo.rules')} />
      {#if draft.opened && draft.opened.at > nowTs() - 7 * 86400}
        <p class="hint state">{t('memo.openedBy', { name: draft.opened.by ?? '—', when: when(draft.opened.at) })}</p>
      {/if}
      {#if draft.later.length || later}
        <Group footnote={t('memo.laterHint', { n: draft.later.length })}>
          <Row title={t('memo.later')} accessory="switch" checked={later} onchange={(on) => { later = on; load(); }} />
        </Group>
      {/if}
      {#if draft.text}
        <!-- items without an event: a small form writes the paragraph, it goes in before the signature -->
        <h3 class="cap">{t('memo.add')}</h3>
        <div class="adds">
          {#each ITEMS as k (k)}<Button kind="tinted" size="s" onclick={() => sheets.memoItem(org, k, draft!.from, put)}>{#snippet icon()}<Plus size={15} />{/snippet}{t(`memo.${k}`)}</Button>{/each}
          <Button kind="tinted" size="s" onclick={() => put('')}>{#snippet icon()}<Plus size={15} />{/snippet}{t('memo.ownItem')}</Button>
        </div>
        <div bind:this={areaBox}><Field label={t('memo.letterText')} multiline rows={16} bind:value={text} /></div>
        {#if draft.guests}<p class="hint">{t('memo.speakers')}</p>{/if}
      {/if}
      {#if draft.print}
        {@const pr = draft.print}
        <h3 class="cap">{t('memo.printTitle')}</h3>
        <p class="hint">{t('memo.attach')}</p>
        <Field label={t('memo.letterText')} multiline rows={10} bind:value={printText} />
        <Button kind="secondary" size="m" full onclick={() => outlook(pr.to, pr.subject, printText)}>{#snippet icon()}<Mail size={17} />{/snippet}{t('memo.outlook')}</Button>
        <Button kind="plain" full onclick={() => copy(printText)}>{#snippet icon()}<Copy size={16} />{/snippet}{t('memo.copy')}</Button>
      {/if}

      <!-- my signature: the Latin name and the positions, fixed once -->
      {#if signing}
        <h3 class="cap">{t('memo.sign')}</h3>
        <Field label={t('memo.nameEn')} bind:value={signing.nameEn} maxlength={120} placeholder={draft.sign.nameEn} />
        {#each ['kk', 'ru', 'en'] as const as l (l)}
          <Field label={t(`memo.pos.${l}`)} bind:value={signing[l]} maxlength={120} placeholder={draft.sign[l]} />
        {/each}
        <Button kind="primary" size="m" full onclick={saveSign}>{t('common.save')}</Button>
      {:else}
        <Group>
          <Row title={draft.sign.nameEn} subtitle={`${t('memo.sign')} · ${draft.sign.ru}`}
            onclick={() => (signing = { nameEn: draft!.sign.nameEn, kk: draft!.sign.kk, ru: draft!.sign.ru, en: draft!.sign.en })}>
            {#snippet detail()}<span class="pen"><Pencil size={17} /></span>{/snippet}
          </Row>
        </Group>
      {/if}

      {#if draft.sent.length}
        <Group caption={t('memo.sent')}>
          {#each draft.sent as e (e.id)}
            <Row dense title={e.title} subtitle={t('memo.sentBy', { name: e.sentBy ?? '—', when: when(e.sentAt ?? 0) })}>
              {#snippet trailing()}<Button kind="gray" size="s" onclick={() => again(e.id)}>{t('memo.again')}</Button>{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}
      {#if draft.without.length}
        <Group caption={t('memo.without')}>
          {#each draft.without as e (e.id)}
            <Row dense title={e.title} subtitle={`${relDay(e.startsAt)}, ${time(e.startsAt)}${e.draft ? ' · ' + t('memo.draft') : ''}`}
              accessory={draft.canEdit ? 'chevron' : 'none'} onclick={draft.canEdit ? () => sheets.editor(org, e.id) : undefined} />
          {/each}
        </Group>
      {/if}
    </div>
  {/if}

  {#snippet footer()}
    {#if draft?.text}
      <Button kind="primary" size="l" full onclick={toDmp}>{#snippet icon()}<Mail size={18} />{/snippet}{t('memo.outlook')}</Button>
      <Button kind="plain" full onclick={copyDmp}>{#snippet icon()}<Copy size={16} />{/snippet}{t('memo.copy')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .stack { display: flex; flex-direction: column; gap: var(--s-3); }
  .stack > :global(section) { margin-top: var(--s-3); }
  .hint { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  .state { color: var(--accent-text); }
  /* a heading in Group's caption style, over what isn't a list */
  .cap { margin: var(--s-3) var(--s-1) -2px; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .adds { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .pen { display: inline-flex; color: var(--text-3); }
</style>
