<script lang="ts" module>
  import type { EventFull, Id } from '../../lib/api';
  /** what the editor hands its redesigned looks: its own state and actions (EventEditor.svelte keeps every rule) */
  export type Ed = {
    f: any; err: Record<string, string>; tried: boolean; live: boolean; busy: string; startTs: number; canPrice: boolean;
    saved: EventFull | null; uploading: boolean; example: { title: string; place: string }; org: Id; pick: string;
    pickPhoto: (e: Event) => void; placeTyped: () => void; submit: (k: 'publish' | 'draft' | 'save') => void; remove: () => void;
  };
</script>

<script lang="ts">
  // The event editor's redesign, stage 1 (the owner picks one before it's built for real): two looks over the same
  // form, behind a dev-only switch (EventEditor.svelte). A: Luma's create screen, tinted by the event, rows that open a
  // focused panel, a check before publishing in a panel of its own. B: one calm page of iOS groups, everything edited in
  // place, the check's notes under the group they're about. Both: Free or Paid is a choice in sight, never a hidden switch
  // (a trip went out free while its text said 7500 tenge), and the check runs on the phone (lib/eventCheck.ts).
  // ponytail: mocks; questions, video, partner and the memo's pickers say "not wired" until a look is chosen
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import AlignLeft from '@lucide/svelte/icons/align-left';
  import Ticket from '@lucide/svelte/icons/ticket';
  import Users from '@lucide/svelte/icons/users';
  import Clock from '@lucide/svelte/icons/clock';
  import Globe from '@lucide/svelte/icons/globe';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import Phone from '@lucide/svelte/icons/phone';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ChevronsUpDown from '@lucide/svelte/icons/chevrons-up-down';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import Poster from '../../ui/Poster.svelte';
  import Button from '../../ui/Button.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import { menu } from '../../ui/menu';
  import { api, ApiErr } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { relDay, nowTs, weekdayShort, dayMonthShort } from '../../lib/time';
  import { shade } from '../../lib/color';
  import { fmtPhone } from '../../lib/phone';
  import { haptic } from '../../lib/tg';
  import { check, type Finding } from '../../lib/eventCheck';

  let { look, ed }: { look: 'a' | 'b'; ed: Ed } = $props();

  const found = $derived(check({ title: ed.f.title, description: ed.f.description, paid: ed.f.paid, price: ed.f.paid ? +ed.f.price || null : null,
    tba: ed.f.tba, place: ed.f.place, startTs: ed.startTs, now: nowTs(), live: ed.live, cover: !!ed.f.cover, seats: +ed.f.seats || null }));
  let moreOpen = $state(false);
  let checked = $state(false); // B: the notes show after the first check, never while the form is being filled
  const money = (n: number) => t('ex.tenge', { n: n.toLocaleString('ru-RU') });
  const priceVal = $derived(ed.f.paid && +ed.f.price > 0 ? money(+ed.f.price) : t('ex.free'));
  const seatsVal = $derived(+ed.f.seats > 0 ? ed.f.seats : t('ex.unlimited'));
  const regVal = $derived(ed.f.deadline && ed.f.regDate ? relDay(Date.parse(ed.f.regDate) / 1000) + ', ' + ed.f.regTime : t('ex.untilStart'));
  const dayText = $derived(Number.isFinite(ed.startTs) ? `${weekdayShort(ed.startTs)}, ${dayMonthShort(ed.startTs)}` : '—');
  const entry = $derived<'free' | 'paid'>(ed.f.paid ? 'paid' : 'free');

  // a note's one-tap fix: it changes the form, or takes the person to the one field that needs them
  function fix(x: Finding) {
    haptic.tap();
    if (x.id === 'priceText') { ed.f.paid = true; ed.f.price = String(x.n); if (look === 'a') ed.pick = 'price'; }
    else if (x.id === 'priceDiff') ed.f.price = String(x.n);
    else if (x.id === 'seatsText') ed.f.seats = String(x.n);
    else if (x.id === 'noPlace') { ed.f.tba = false; go('place'); }
    else if (x.id === 'noAbout') go('about');
    else if (x.id === 'past') { ed.pick = ''; try { (document.querySelector('.lk input[type=date]') as HTMLInputElement)?.showPicker(); } catch { /* old webviews: the field is in sight */ } }
    else if (x.id === 'longTitle') { ed.pick = ''; (document.querySelector('.lk .name') as HTMLElement)?.focus(); }
  }
  function go(what: 'place' | 'about') {
    if (look === 'a') ed.pick = what;
    else (document.querySelector(`.lk [data-f=${what}]`) as HTMLElement)?.focus();
  }
  const fixLabel = (x: Finding) => x.id === 'priceText' ? t('ex.fix.paid', { n: (x.n).toLocaleString('ru-RU') }) : x.id === 'priceDiff' ? t('ex.fix.price', { n: x.n.toLocaleString('ru-RU') })
    : x.id === 'seatsText' ? t('ex.fix.seats', { n: x.n }) : t(`ex.fix.${({ past: 'time', noPlace: 'place', noCover: 'cover', noAbout: 'about', longTitle: 'title' } as const)[x.id]}`);
  const noteText = (x: Finding) => 'n' in x ? t(`ex.f.${x.id}`, { n: x.n.toLocaleString('ru-RU') }) : t(`ex.f.${x.id}`);
  const SERIOUS = new Set(['priceText', 'priceDiff', 'past', 'seatsText']);

  // A publishes after the check: nothing found goes straight out, else the panel; B shows the notes in place first
  function publish() {
    if (found.length && look === 'a') { haptic.tap(); ed.pick = 'check'; return; }
    if (found.length && look === 'b' && !checked) { haptic.error(); checked = true; scrollToNote(); return; }
    ed.pick = '';
    ed.submit(ed.live ? 'save' : 'publish');
  }
  function runCheck() { haptic.tap(); checked = true; scrollToNote(); }
  function scrollToNote() { requestAnimationFrame(() => (document.querySelector('.lk .note.serious') ?? document.querySelector('.lk .note'))?.scrollIntoView({ behavior: 'smooth', block: 'center' })); }
  const notesFor = (ids: string[]) => (checked ? found.filter((x) => ids.includes(x.id)) : []);

  // the AI writes the description from a few words (the editor's announcement fill, its description only)
  let writing = $state(false);
  let suggestion = $state('');
  async function aiWrite() {
    haptic.tap(); writing = true;
    try {
      const x = await api.eventFill(ed.org, `${ed.f.title}. ${ed.f.description}`.trim());
      if (x.description) suggestion = x.description; else say(t('ed.fillNone'), 'thinking_face_3d');
    } catch (e) {
      const c = e instanceof ApiErr ? e.code : '';
      say(t(c === 'rate_limited' ? 'as.limit' : c === 'unavailable' ? 'as.busy' : c === 'bad_input' ? 'ed.fillShort' : 'common.error'), 'warning_3d');
    } finally { writing = false; }
  }

  const who = (el: Element) => menu(el, [
    { label: t('ed.whoAll'), checked: !ed.f.teamOnly, onselect: () => { ed.f.teamOnly = false; } },
    { label: t('ed.whoTeam'), checked: ed.f.teamOnly, onselect: () => { ed.f.teamOnly = true; } },
  ], 'end');
  const TITLES: Record<string, string> = { place: 'ed.place', about: 'ed.about', price: 'ex.price', seats: 'ed.seats', reg: 'ex.regUntil', more: 'ex.more', check: 'ex.checkTitle' };
</script>

<!-- ============ shared pieces ============ -->
{#snippet coverInput()}<input type="file" accept="image/*" onchange={ed.pickPhoto} disabled={ed.uploading} />{/snippet}

{#snippet notes(list: Finding[])}
  {#each list as x (x.id)}
    <div class="note" class:serious={SERIOUS.has(x.id)}>
      <span class="ni">{#if SERIOUS.has(x.id)}<TriangleAlert size={17} />{:else}<Sparkles size={16} />{/if}</span>
      <span class="nt">{noteText(x)}</span>
      {#if x.id === 'noCover'}<label class="nfix">{fixLabel(x)}{@render coverInput()}</label>
      {:else}<button class="nfix" onclick={() => fix(x)}>{fixLabel(x)}</button>{/if}
    </div>
  {/each}
{/snippet}

{#snippet entrySeg()}
  {#if ed.canPrice}
    <Segmented items={[{ value: 'free', label: t('ex.free') }, { value: 'paid', label: t('ex.paidSeg') }]} value={entry} label={t('ex.entry')}
      onchange={(v) => { ed.f.paid = v === 'paid'; }} />
  {/if}
{/snippet}

{#snippet payFields()}
  <label class="field" class:bad={ed.tried && ed.err.price}><span class="t-cap">{t('ed.price')}</span>
    <input bind:value={ed.f.price} type="number" inputmode="numeric" min="1" placeholder="2000" /></label>
  <label class="field" class:bad={ed.tried && ed.err.payTo}><span class="t-cap">{t('ed.payTo')}</span>
    <input bind:value={ed.f.payTo} maxlength="80" placeholder={t('ed.payToPh')} /></label>
  <label class="field" class:bad={ed.tried && ed.err.payPhone}><span class="t-cap">{t('ed.payPhone')}</span>
    <input bind:value={ed.f.payPhone} oninput={() => (ed.f.payPhone = fmtPhone(ed.f.payPhone))} type="tel" inputmode="tel" placeholder="+7 (707) 123 45 67" /></label>
  <p class="hint">{t('ed.payHint')}</p>
{/snippet}

{#snippet aiBlock()}
  {#if session.board}
    {#if suggestion}
      <div class="sug">
        <span class="t-cap"><Sparkles size={13} /> {t('ex.aiSuggest')}</span>
        <p>{suggestion}</p>
        <div class="btns"><Button kind="gray" size="s" onclick={() => (suggestion = '')}>{t('ex.aiKeep')}</Button>
          <Button kind="tinted" size="s" onclick={() => { ed.f.description = suggestion; suggestion = ''; haptic.ok(); }}>{t('ex.aiUse')}</Button></div>
      </div>
    {:else}
      <button class="ai" disabled={writing} class:busy={writing} onclick={aiWrite}><Sparkles size={16} />{writing ? t('as.thinking') + '…' : t('ex.aiWrite')}</button>
      {#if !ed.f.description.trim()}<p class="hint">{t('ex.aiHint')}</p>{/if}
    {/if}
  {/if}
{/snippet}

{#if look === 'a'}
<!-- ============ A: Luma, tinted ============ -->
<div class="lk a" style:--tint={shade(ed.f.color)}>
  <div class="wash" aria-hidden="true">{#if ed.f.cover}<img src={ed.f.cover.thumb} alt="" />{/if}<i></i></div>
  <div class="body scroll">
    <label class="art" class:busy={ed.uploading}>
      <Poster item={{ cover: ed.f.cover, emoji: ed.f.emoji, color: ed.f.color }} size={196} radius={24} />
      <span class="artbtn glass glass-pill"><ImagePlus size={20} /></span>
      {@render coverInput()}
    </label>
    <textarea class="name" rows="1" bind:value={ed.f.title} maxlength="80" placeholder={t('ex.name')}></textarea>
    {#if ed.tried && ed.err.title}<p class="err">{ed.err.title}</p>{/if}

    <div class="pill when">
      <i class="line" aria-hidden="true"></i>
      <!-- Luma's one line of text ("Mon, 9 Nov  18:00"); the phone's own pickers sit under each part -->
      <div class="wr"><span class="dot"></span><b>{t('ed.start')}</b>
        <label class="tv">{dayText}<input type="date" bind:value={ed.f.date} /></label><label class="tv">{ed.f.start || '—'}<input type="time" bind:value={ed.f.start} /></label></div>
      <div class="wr"><span class="dot o"></span><b>{t('ed.end')}</b><label class="tv" class:ph={!ed.f.end}>{ed.f.end || '—'}<input type="time" bind:value={ed.f.end} /></label></div>
    </div>
    {#if ed.tried && ed.err.when}<p class="err">{ed.err.when}</p>{/if}

    <button class="pill go" onclick={() => (ed.pick = 'place')}><MapPin size={20} />
      <span class:ph={!ed.f.place.trim()} class="ellipsis">{ed.f.place.trim() || (ed.f.tba ? t('ed.tba') : t('ex.placeAdd'))}</span></button>
    <button class="pill go" onclick={() => (ed.pick = 'about')}><AlignLeft size={20} />
      <span class:ph={!ed.f.description.trim()} class="clamp-2">{ed.f.description.trim() || t('ex.aboutAdd')}</span></button>

    <h3 class="cap">{t('ex.tickets')}</h3>
    <div class="pill grp">
      <button class="r" onclick={() => (ed.pick = 'price')}><Ticket size={19} /><b>{t('ex.price')}</b><span class="v" class:paid={ed.f.paid}>{priceVal}</span><ChevronRight size={18} /></button>
      <button class="r" onclick={() => (ed.pick = 'seats')}><Users size={19} /><b>{t('ed.seats')}</b><span class="v">{seatsVal}</span><ChevronRight size={18} /></button>
      <button class="r" onclick={() => (ed.pick = 'reg')}><Clock size={19} /><b>{t('ex.regUntil')}</b><span class="v">{regVal}</span><ChevronRight size={18} /></button>
    </div>

    <h3 class="cap">{t('ex.options')}</h3>
    <div class="pill grp">
      <button class="r" onclick={(e) => who(e.currentTarget.querySelector('.v')!)}><Globe size={19} /><b>{t('ex.who')}</b>
        <span class="v">{ed.f.teamOnly ? t('ed.whoTeam') : t('ed.whoAll')}</span><ChevronsUpDown size={16} /></button>
      <label class="r"><GraduationCap size={19} /><b>{t('ed.firstYear')}</b><span class="sw-on"><input type="checkbox" role="switch" bind:checked={ed.f.firstYear} /></span></label>
      <label class="r"><Phone size={19} /><b>{t('ed.needsPhone')}</b><span class="sw-on"><input type="checkbox" role="switch" bind:checked={ed.f.needsPhone} /></span></label>
      <button class="r" onclick={() => (ed.pick = 'more')}><Ellipsis size={19} /><b>{t('ex.more')}</b><span class="v"></span><ChevronRight size={18} /></button>
    </div>
    <div class="tail"></div>
  </div>

  <footer class="foot btns glass glass-sheet" class:hide={!!ed.pick}>
    {#if !ed.live}<Button kind="gray" size="l" full loading={ed.busy === 'draft'} onclick={() => ed.submit('draft')}>{t('ed.saveDraft')}</Button>{/if}
    <Button kind="filled" size="l" full loading={ed.busy === 'publish' || ed.busy === 'save'} onclick={publish}>{ed.live ? t('common.save') : t('ed.publish')}</Button>
  </footer>
</div>

{:else}
<!-- ============ B: one page of groups, edited in place ============ -->
<div class="lk b">
  <div class="body scroll">
    <label class="hero" class:busy={ed.uploading}>
      <Poster item={{ cover: ed.f.cover, emoji: ed.f.emoji, color: ed.f.color }} big radius={22} />
      <span class="herobtn glass glass-pill"><ImagePlus size={17} />{t('ed.cover')}</span>
      {@render coverInput()}
    </label>
    {@render notes(notesFor(['noCover']))}
    <textarea class="name" rows="1" bind:value={ed.f.title} maxlength="80" placeholder={t('ex.name')}></textarea>
    {@render notes(notesFor(['longTitle']))}

    <Group caption={t('ex.when')}>
      <Row title={t('ed.date')} trailing={dateIn} />
      <Row title={t('ed.start')} trailing={startIn} />
      <Row title={t('ed.end')} trailing={endIn} />
    </Group>
    {@render notes(notesFor(['past']))}

    <Group caption={t('ex.where')}>
      <label class="inrow kb-row lead"><MapPin size={19} /><input data-f="place" bind:value={ed.f.place} oninput={ed.placeTyped} maxlength="400" placeholder={ed.example.place} disabled={ed.f.tba} /></label>
      <Row title={t('ed.tba')} accessory="switch" checked={ed.f.tba} onchange={(v) => (ed.f.tba = v)} />
    </Group>
    {@render notes(notesFor(['noPlace']))}

    <Group caption={t('ex.entry')}>
      {#if ed.canPrice}<div class="segrow kb-row">{@render entrySeg()}</div>{/if}
      {#if ed.f.paid}
        <label class="inrow kb-row"><b>{t('ex.price')}</b><input bind:value={ed.f.price} type="number" inputmode="numeric" placeholder="2000" /><span class="unit">₸</span></label>
        <label class="inrow kb-row"><b>{t('ed.payTo')}</b><input bind:value={ed.f.payTo} maxlength="80" /></label>
        <label class="inrow kb-row"><b>{t('ed.payPhone')}</b><input bind:value={ed.f.payPhone} oninput={() => (ed.f.payPhone = fmtPhone(ed.f.payPhone))} type="tel" inputmode="tel" placeholder="+7 707 …" /></label>
      {/if}
      <label class="inrow kb-row"><b>{t('ed.seats')}</b><input bind:value={ed.f.seats} type="number" inputmode="numeric" placeholder={t('ex.unlimited')} /></label>
    </Group>
    {@render notes(notesFor(['priceText', 'priceDiff', 'seatsText']))}

    <Group caption={t('ed.about')}>
      <textarea class="about" data-f="about" bind:value={ed.f.description} maxlength="2000" rows="5" placeholder={t('ed.aboutPh')}></textarea>
    </Group>
    {@render notes(notesFor(['noAbout']))}
    {@render aiBlock()}

    <Group>
      <Row title={t('ex.more')} subtitle={t('ex.extras')} accessory="disclosure" open={moreOpen} onclick={() => (moreOpen = !moreOpen)} />
      {#if moreOpen}
        <Row title={t('ed.teamOnly')} accessory="switch" checked={ed.f.teamOnly} onchange={(v) => (ed.f.teamOnly = v)} />
        <Row title={t('ed.firstYear')} accessory="switch" checked={ed.f.firstYear} onchange={(v) => (ed.f.firstYear = v)} />
        <Row title={t('ed.needsPhone')} accessory="switch" checked={ed.f.needsPhone} onchange={(v) => (ed.f.needsPhone = v)} />
        <Row title={t('ed.deadline')} accessory="switch" checked={ed.f.deadline} onchange={(v) => (ed.f.deadline = v)} />
        <Row title={t('ed.albumOpen')} accessory="switch" checked={ed.f.albumOpen} onchange={(v) => (ed.f.albumOpen = v)} />
        <Row title={t('ed.vol')} accessory="switch" checked={ed.f.vol} onchange={(v) => (ed.f.vol = v)} />
        <Row title={t('ed.form')} value={t('ex.later')} />
      {/if}
    </Group>
    <div class="tail"></div>
  </div>

  <footer class="foot btns glass glass-sheet" class:hide={!!ed.pick}>
    <Button kind="tinted" size="l" onclick={runCheck}>{#snippet icon()}<Sparkles size={18} />{/snippet}{t('ex.check')}</Button>
    <Button kind="filled" size="l" full loading={ed.busy === 'publish' || ed.busy === 'save'} onclick={publish}>
      {checked && found.length && !ed.live ? t('ex.publishAnyway') : ed.live ? t('common.save') : t('ed.publish')}</Button>
  </footer>
</div>
{/if}

{#snippet dateIn()}<label class="tv">{dayText}<input type="date" bind:value={ed.f.date} /></label>{/snippet}
{#snippet startIn()}<label class="tv">{ed.f.start || '—'}<input type="time" bind:value={ed.f.start} /></label>{/snippet}
{#snippet endIn()}<label class="tv" class:ph={!ed.f.end}>{ed.f.end || '—'}<input type="time" bind:value={ed.f.end} /></label>{/snippet}

<!-- ============ A's focused panels (Telegram's Back closes one: EventEditor) ============ -->
{#if look === 'a' && ed.pick}
  <button class="scrim" onclick={() => (ed.pick = '')} aria-label={t('common.close')}></button>
  <div class="pk glass glass-sheet">
    <header class="pkh"><b>{t(TITLES[ed.pick] as 'ex.price')}</b>
      {#if ed.pick !== 'check'}<Button kind="tinted" size="s" onclick={() => (ed.pick = '')}>{t('ex.done')}</Button>{/if}</header>
    <div class="pkb scroll">
      {#if ed.pick === 'place'}
        <label class="field"><span class="t-cap">{t('ed.place')}</span>
          <input bind:value={ed.f.place} oninput={ed.placeTyped} maxlength="400" placeholder={ed.example.place} disabled={ed.f.tba} /></label>
        <label class="switch"><span><b>{t('ed.tba')}</b><i class="t-foot">{t('ed.tbaHint')}</i></span><input type="checkbox" role="switch" bind:checked={ed.f.tba} /></label>
        <p class="hint">{t('ed.placeHint')}</p>
      {:else if ed.pick === 'about'}
        <label class="field"><textarea bind:value={ed.f.description} maxlength="2000" rows="7" placeholder={t('ed.aboutPh')}></textarea></label>
        {@render aiBlock()}
      {:else if ed.pick === 'price'}
        {#if ed.canPrice}
          {@render entrySeg()}
          {#if ed.f.paid}{@render payFields()}{:else}<p class="hint">{t('ed.paidHint')}</p>{/if}
        {:else}<p class="hint">{t('ed.paidOfficial')}</p>{/if}
      {:else if ed.pick === 'seats'}
        <label class="field"><span class="t-cap">{t('ed.seats')}</span><input bind:value={ed.f.seats} type="number" inputmode="numeric" min="1" placeholder={t('ex.unlimited')} /></label>
      {:else if ed.pick === 'reg'}
        <label class="switch"><span><b>{t('ed.deadline')}</b><i class="t-foot">{t('ed.deadlineHint')}</i></span><input type="checkbox" role="switch" bind:checked={ed.f.deadline} /></label>
        {#if ed.f.deadline}<div class="two"><label class="field"><span class="t-cap">{t('ed.regDate')}</span><input type="date" bind:value={ed.f.regDate} /></label>
          <label class="field"><span class="t-cap">{t('ed.regTime')}</span><input type="time" bind:value={ed.f.regTime} /></label></div>{/if}
      {:else if ed.pick === 'more'}
        <Group footnote={t('ex.later')}>
          <Row title={t('ed.albumOpen')} accessory="switch" checked={ed.f.albumOpen} onchange={(v) => (ed.f.albumOpen = v)} />
          <Row title={t('ed.vol')} accessory="switch" checked={ed.f.vol} onchange={(v) => (ed.f.vol = v)} />
          <Row title={t('ed.form')} accessory="chevron" onclick={() => {}} />
          <Row title={t('ed.video')} accessory="chevron" onclick={() => {}} />
          <Row title={t('ed.partner')} accessory="chevron" onclick={() => {}} />
        </Group>
      {:else if ed.pick === 'check'}
        {#if found.length}
          <p class="sum">{tn('ex.found', found.length)}</p>
          {@render notes(found)}
        {:else}
          <p class="okay"><CircleCheck size={20} />{t('ex.checkOk')}</p>
        {/if}
        <div class="pkfoot">
          <Button kind="filled" size="l" full loading={ed.busy === 'publish'} onclick={() => { ed.pick = ''; ed.submit(ed.live ? 'save' : 'publish'); }}>
            {found.length ? t('ex.publishAnyway') : t('ed.publish')}</Button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .lk { position: absolute; inset: 0; display: flex; flex-direction: column; }
  .body { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; gap: var(--s-3); margin-top: max(48px, var(--top)); padding: var(--s-2) var(--gutter) 0; }
  .body > :global(*) { flex-shrink: 0; }
  .tail { height: calc(var(--safe-bottom) + 96px); }
  .foot { position: absolute; left: 10px; right: 10px; bottom: calc(var(--safe-bottom) + 10px); display: flex; gap: var(--s-2); padding: var(--s-2); border-radius: var(--r-xl); }
  .foot > :global(.btn:first-child:not(:last-child)) { flex: 0.6 1 0; } /* the publish gets the room: its label whole at 320 */
  .foot.hide { opacity: 0; pointer-events: none; }
  input[type=file] { position: absolute; inset: 0; opacity: 0; }
  .ph { color: var(--text-3); }
  .err { margin: -6px var(--s-4) 0; font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--danger-text); }
  .hint { margin: 0 var(--s-1); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  .name { width: 100%; resize: none; field-sizing: content; min-height: 1.2em; color: var(--text); background: none;
    font: 700 var(--fs-t1)/1.18 var(--font-display); letter-spacing: -0.02em; }
  .name::placeholder { color: var(--text-3); }

  /* --- A --- */
  .a { --pill: var(--surface-2); background: var(--bg); overflow: hidden; }
  :global(:root[data-theme='light']) .a { --pill: rgba(255, 255, 255, 0.62); }
  .wash { position: absolute; inset: 0; background: var(--tint); overflow: hidden; }
  .wash img { position: absolute; inset: -20%; width: 140%; height: 140%; object-fit: cover; filter: blur(48px) saturate(1.3); }
  .wash i { position: absolute; inset: 0; background: var(--bg); opacity: 0.5; }
  :global(:root[data-theme='light']) .wash i { opacity: 0.72; }
  .art { position: relative; align-self: center; margin: var(--s-1) 0 var(--s-2); border-radius: var(--r-xl); box-shadow: var(--shadow-card); }
  .art.busy { opacity: 0.6; }
  .artbtn { position: absolute; right: -8px; bottom: -8px; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; color: var(--text); }
  .a .name { padding: var(--s-3) var(--s-4); border-radius: var(--r-l); background: var(--pill); }
  .pill { position: relative; display: flex; align-items: center; gap: var(--s-3); width: 100%; min-height: 54px; padding: 0 var(--s-4);
    border-radius: var(--r-l); background: var(--pill); color: var(--text); text-align: left; font: 500 var(--fs-row)/1.3 var(--font-text); }
  .pill > :global(svg) { flex: none; color: var(--text-2); }
  .go { padding-block: var(--s-3); }
  .go > span { flex: 1; min-width: 0; }
  .go:active, .r:active { opacity: 0.7; transform: none; }
  .when { flex-direction: column; align-items: stretch; gap: 0; padding: 0; }
  .wr { position: relative; display: flex; align-items: center; gap: var(--s-2); min-height: 54px; padding: 0 var(--s-4) 0 44px; }
  .wr + .wr::before { content: ''; position: absolute; left: 44px; right: 0; top: 0; height: 0.5px; background: var(--separator); }
  .wr b { flex: 1; font-weight: 500; color: var(--text-2); }
  .tv { position: relative; flex: none; padding: 7px 8px; border-radius: var(--r-xs); background: var(--fill); color: var(--text); font: 600 var(--fs-body)/1 var(--font-text); white-space: nowrap; }
  .tv input { position: absolute; inset: 0; width: 100%; opacity: 0; }
  .dot { position: absolute; left: 20px; width: 9px; height: 9px; border-radius: 50%; background: var(--text-2); }
  .dot.o { background: none; box-shadow: inset 0 0 0 1.5px var(--text-2); }
  .line { position: absolute; left: 24px; top: 33px; bottom: 33px; border-left: 1.5px dotted var(--text-3); }
  .cap { margin: var(--s-3) var(--s-1) calc(-1 * var(--s-1)); font: 650 var(--fs-body)/1.2 var(--font-text); color: var(--text-2); }
  .grp { flex-direction: column; align-items: stretch; gap: 0; padding: 0; }
  .r { position: relative; display: flex; align-items: center; gap: var(--s-3); min-height: 54px; padding: 0 var(--s-4); text-align: left; color: var(--text); }
  .r + .r::before { content: ''; position: absolute; left: 47px; right: 0; top: 0; height: 0.5px; background: var(--separator); }
  .r > :global(svg) { flex: none; color: var(--text-2); }
  .r b { flex: 1 1 auto; min-width: 0; font-weight: 500; }
  .r .v { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); font-weight: 500; }
  .r .v.paid { color: var(--text); font-weight: 650; }
  .r > :global(svg:last-child) { color: var(--text-3); }

  /* --- B --- */
  .b { background: var(--bg); }
  .hero { position: relative; display: block; width: 100%; aspect-ratio: 16 / 10; border-radius: var(--r-l); overflow: hidden; }
  .hero.busy { opacity: 0.6; }
  .herobtn { position: absolute; right: var(--s-3); bottom: var(--s-3); display: inline-flex; align-items: center; gap: 6px; height: var(--btn-s); padding: 0 var(--s-3);
    border-radius: var(--r-full); color: var(--text); font: 600 var(--fs-sub)/1 var(--font-text); }
  .b .name { padding: var(--s-1) var(--s-1) 0; }
  .b :global(.grp) { margin-top: var(--s-2); }
  .inrow { position: relative; display: flex; align-items: center; gap: var(--s-3); min-height: var(--row-h); padding: 0 var(--s-4); color: var(--text); font: 450 var(--fs-row)/1.25 var(--font-text); }
  :global(.kb-row) + .inrow::before { content: ''; position: absolute; left: var(--s-4); right: 0; top: 0; height: 0.5px; background: var(--separator); }
  .inrow > :global(svg) { flex: none; color: var(--text-3); }
  .inrow b { flex: none; font-weight: 450; }
  .inrow input { flex: 1; min-width: 0; text-align: right; color: var(--text-2); font: inherit; }
  .inrow.lead input { text-align: left; color: var(--text); }
  .inrow input:disabled { opacity: 0.4; }
  .unit { color: var(--text-3); }
  .segrow { padding: var(--s-3) var(--s-4); }
  .about { width: 100%; min-height: 120px; padding: var(--s-3) var(--s-4); resize: none; color: var(--text); font: 450 var(--fs-row)/1.4 var(--font-text); background: none; }

  /* --- notes, the AI --- */
  .note { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2) var(--s-3); padding: var(--s-3) var(--s-3) var(--s-3) var(--s-4); border-radius: var(--r-m);
    background: var(--surface-2); animation: note-in 300ms var(--ease-spring) backwards; }
  @keyframes note-in { from { opacity: 0; transform: translateY(-4px); } }
  .note.serious { background: var(--warning-soft); }
  .ni { flex: none; display: inline-flex; color: var(--text-3); }
  .serious .ni { color: var(--warning-text); }
  .nt { flex: 1 1 160px; min-width: 0; font: 550 var(--fs-body)/1.35 var(--font-text); color: var(--text); }
  .nfix { position: relative; overflow: hidden; flex: none; margin-left: auto; height: var(--btn-s); padding: 0 var(--s-3); border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 var(--fs-sub)/var(--btn-s) var(--font-text); white-space: nowrap; }
  .serious .nfix { background: var(--accent); color: var(--on-accent); }
  .ai { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; height: var(--btn-s); padding: 0 var(--s-3); border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 var(--fs-sub)/1 var(--font-text); }
  .ai.busy { opacity: 0.6; }
  .sug { display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); border-radius: var(--r-m); background: var(--accent-soft);
    animation: note-in 300ms var(--ease-spring) backwards; }
  .sug .t-cap { display: inline-flex; align-items: center; gap: 4px; color: var(--accent-text); }
  .sug p { font: 450 var(--fs-body)/1.45 var(--font-text); color: var(--text); white-space: pre-line; }
  .sug .btns { display: flex; gap: var(--s-2); justify-content: flex-end; }

  /* --- A's panels --- */
  .scrim { position: absolute; inset: 0; background: var(--scrim); animation: fade 220ms var(--ease) backwards; }
  @keyframes fade { from { opacity: 0; } }
  .pk { position: absolute; left: 8px; right: 8px; bottom: calc(var(--safe-bottom) + 8px); max-height: 78%; display: flex; flex-direction: column;
    border-radius: var(--r-xl); animation: rise 380ms var(--ease-spring) backwards; }
  @keyframes rise { from { transform: translate3d(0, 100%, 0); } }
  .pkh { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); padding: var(--s-4) var(--s-4) var(--s-2) var(--s-5); }
  .pkh b { font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.015em; }
  .pkb { display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-2) var(--s-4) var(--s-4); }
  .pkb > :global(*) { flex-shrink: 0; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
  .sum { margin: 0 var(--s-1); font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .okay { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-1); font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--success-text); }
  .pkfoot { display: flex; margin-top: var(--s-1); }
</style>
