<script lang="ts">
  // One session's door in the volunteers ledger (server logic/vol.py), for who runs it: the President, a Vice, or the
  // member the door was handed to. After Finish: everyone who left without checking out, one answer each ("was here
  // until the end" or the time they left, between their check-in and Finish); the app counts the minutes. Before it, for
  // the President and Vice: the one-time link that hands this session's door to a club member, who holds it, taking it back.
  import { copyText } from '../../ui/copy';
  import { api, type Id, type VolDoor } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { loadVol } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { dateInput, fromInputs, time } from '../../lib/time';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, sid, title }: { overlay: Overlay; sid: Id; title: string } = $props();
  let d = $state<VolDoor | null>(null);
  let gone = $state(false);   // not mine (any more)
  let link = $state('');      // the link just made: its token is given once
  let pick = $state<Id>(0);   // whose "left at" time is being picked
  let hm = $state('');
  let redo = $state<Id>(0);   // an answered one being answered again
  $effect(() => { api.volDoor(sid).then((x) => (d = x)).catch(() => (gone = true)); });
  type One = VolDoor['unmarked'][number];
  const todo = $derived((d?.unmarked ?? []).filter((x) => x.outAt === null || x.id === redo));
  const answered = $derived((d?.unmarked ?? []).filter((x) => x.outAt !== null && x.id !== redo));

  async function write(f: () => Promise<VolDoor>, next: VolDoor) {
    const was = d;
    d = next; // at once; back if the server says no
    haptic.tap();
    try { d = await f(); haptic.ok(); void loadVol(); }
    catch { d = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  function answer(x: One, left: number | null) {
    if (!d) return;
    pick = 0; redo = 0;
    void write(() => api.volResolve(x.id, left), { ...d, unmarked: d.unmarked.map((y) => (y.id === x.id ? { ...y, outAt: left ?? x.end } : y)) });
  }
  function leftAt(x: One) {
    // the time alone: on the check-in's day, or past midnight when it reads earlier than the check-in
    let at = fromInputs(dateInput(x.inAt), hm);
    if (at < x.inAt - (x.inAt % 60)) at += 86400;
    if (!hm || !Number.isFinite(at) || at > x.end) { haptic.error(); say(t('ledg.leftRange', { from: time(x.inAt), to: time(x.end) }), 'warning_3d'); return; }
    answer(x, at);
  }

  async function make() {
    haptic.tap();
    try {
      const got = await api.volHand(sid);
      d = got; link = `https://t.me/KBTUappBot?startapp=vh_${got.token}`; haptic.ok();
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function copy() {
    if (!(await copyText(link, t('sl.copied')))) say(t('common.error'), 'warning_3d');
  }
  const share = () => { haptic.tap(); openLink(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(t('ledg.handMsg', { title }))}`); };
  async function back() {
    if (!d || !(await sheets.ask({ title: t('ledg.handBackAsk'), text: t('ledg.handBackText'), ok: t('ledg.handBack'), cancel: t('common.cancel'), danger: true }))) return;
    link = '';
    void write(() => api.volUnhand(sid), { ...d, hand: null });
  }
</script>

<Sheet {overlay} icon={DoorOpen} full title={title}>
  {#if gone}
    <EmptyState icon={DoorOpen} title={t('ledg.handDead')} />
  {:else if d}
    <div class="body">
      {#if d.ended}
        <Group caption={t('ledg.doorTitle')} footnote={todo.length ? t('ledg.doorNote') : undefined}>
          {#each todo as x (x.id)}
            <Row dense title={x.name || '—'} subtitle={t('ledg.cameAt', { time: time(x.inAt) })}>
              {#snippet lead()}{#if x.person}<Avatar person={x.person} size={32} tappable={false} />{:else}<span class="blank" aria-hidden="true"></span>{/if}{/snippet}
            </Row>
            {#if x.person?.id === session.me?.id}
              <p class="t-foot own">{t('ledg.ownNo')}</p>
            {:else if pick === x.id}
              <form class="acts" onsubmit={(e) => { e.preventDefault(); leftAt(x); }}>
                <input class="at" type="time" aria-label={t('ledg.leftAt')} min={time(x.inAt)} max={time(x.end)} bind:value={hm} required />
                <Button kind="primary" size="m" full type="submit" disabled={!hm}>{t('common.save')}</Button>
              </form>
            {:else}
              <div class="acts">
                <Button kind="secondary" size="m" full onclick={() => answer(x, null)}>{t('ledg.tillEnd')}</Button>
                <Button kind="secondary" size="m" full onclick={() => { haptic.tap(); hm = time(x.end); pick = x.id; }}>{t('ledg.leftAt')}</Button>
              </div>
            {/if}
          {:else}
            <EmptyState inline text={t('ledg.allDone')} />
          {/each}
        </Group>
        {#if answered.length}
          <Group>
            {#each answered as x (x.id)}
              {#snippet change()}<Button kind="secondary" size="s" onclick={() => { haptic.tap(); pick = 0; redo = x.id; }}>{t('ledg.change')}</Button>{/snippet}
              <Row dense title={x.name || '—'} subtitle={time(x.inAt) + '–' + time(x.outAt ?? x.inAt)} trailing={d.lead && x.person?.id !== session.me?.id ? change : undefined} />
            {/each}
          </Group>
        {/if}
      {/if}

      {#if d.lead && (d.hand || !d.ended)}
        <Group caption={t('ledg.hand')} footnote={link ? t('ledg.handOnce') : t('ledg.handNote')}>
          {#if d.hand}
            {#snippet off()}<Button kind="secondary" size="s" onclick={back}>{t('ledg.handBack')}</Button>{/snippet}
            {#if d.hand.holder}
              {@const h = d.hand.holder}
              <Row dense title={h.name} subtitle={t('ledg.handHolder')} trailing={off}>
                {#snippet lead()}<Avatar person={h} size={32} tappable={false} />{/snippet}
              </Row>
            {:else}
              <Row dense title={t('ledg.handWaiting')} trailing={off} />
            {/if}
            {#if link && !d.hand.holder}
              <div class="acts">
                <Button kind="secondary" size="m" full onclick={copy}>{t('ledg.handCopy')}</Button>
                <Button kind="primary" size="m" full onclick={share}>{t('ledg.handShare')}</Button>
              </div>
            {/if}
          {/if}
          {#if !d.ended && !link && !d.hand?.holder}<Row tone="add" title={t(d.hand ? 'ledg.handNew' : 'ledg.handMake')} onclick={make} />{/if}
        </Group>
      {/if}
    </div>
  {/if}
</Sheet>

<style>
  .body { display: flex; flex-direction: column; gap: var(--s-4); margin-top: var(--s-2); }
  .blank { display: block; width: 32px; height: 32px; border-radius: 50%; background: var(--fill); }
  /* a pair side by side while whole labels fit, else a line each (320 px) */
  .acts { display: flex; flex-wrap: wrap; gap: var(--s-2); padding: 0 var(--s-4) var(--s-3); }
  .acts :global(.btn.full) { flex: 1 1 auto; width: auto; min-width: 0; }
  .own { padding: 0 var(--s-4) var(--s-3); }
  /* Field's look for the time input it can't take (as MemoAsks) */
  .at { flex: 1 1 9em; min-width: 0; min-height: var(--ctl-m); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
</style>
