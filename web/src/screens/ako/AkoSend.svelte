<script lang="ts" module>
  // Contacts already saved in this visit, by link: the wizard remounts this step, and the parent's view isn't told of a patch.
  const kept = new Map<string, { name: string; phone: string; email: string }>();
</script>

<script lang="ts">
  // The last step: contacts (saved when a field is left), what goes, and the send button in its own sticky bar.
  import { untrack } from 'svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import { ako } from '../../lib/api/ako';
  import type { AkoView } from '../../lib/api/types';
  import { i18n } from '../../lib/i18n/index.svelte';
  import { aw, awn, type AkoKey } from '../../lib/i18n/ako';
  import { time, weekday, dayMonth } from '../../lib/time';
  import { errOf, errKey } from './AkoDocs.svelte';

  type F = 'name' | 'phone' | 'email';
  let { view, token, onsent }: { view: AkoView; token: string; onsent: (v: AkoView) => void } = $props();

  const saved = untrack(() => ({ ...(kept.get(token) ?? { name: view.name ?? '', phone: view.phone ?? '', email: view.email ?? '' }) }));
  let name = $state(saved.name);
  let phone = $state(saved.phone);
  let email = $state(saved.email);
  let bad = $state<Record<F, AkoKey | ''>>({ name: '', phone: '', email: '' });
  let busy = $state(false);
  let note = $state('');

  const program = $derived(view.programs.find((p) => p.key === view.program) ?? null);
  const title = $derived(program ? (program.info[i18n.lang] ?? program.info.ru).title : '');
  const docs = $derived(new Set(view.files.map((f) => f.doc)).size);
  const k = (s: string) => s as AkoKey;

  async function flush(): Promise<boolean> {
    const now = { name: name.trim(), phone: phone.trim(), email: email.trim() };
    let ok = true;
    for (const f of ['name', 'phone', 'email'] as const) {
      const v = now[f];
      if (v === saved[f]) continue;
      if (f !== 'email' && !v) continue; // an emptied name or phone: said at sending
      try {
        await ako.patch(token, f === 'name' ? { name: v } : f === 'phone' ? { phone: v } : { email: v });
        saved[f] = v; bad[f] = '';
      } catch (e) {
        ok = false;
        const { code } = errOf(e);
        if (code === 'bad_input' && f !== 'name') bad[f] = f === 'phone' ? 'ako.err.phone' : 'ako.err.email';
        else note = aw(errKey(e));
      }
    }
    kept.set(token, { ...saved });
    return ok;
  }
  // one save at a time: leaving a field and tapping Send at once must not patch twice
  let chain: Promise<boolean> = Promise.resolve(true);
  const save = () => (chain = chain.then(flush, flush));

  async function send() {
    if (busy) return;
    busy = true; note = '';
    try {
      const ok = await save();
      if (!name.trim() || !phone.trim()) { note = aw('ako.needName'); return; }
      if (!ok) { note ||= aw(bad.phone || bad.email || 'ako.err.generic'); return; }
      const v = await ako.submit(token);
      kept.delete(token);
      onsent(v);
    } catch (e) {
      const { code, msg, data } = errOf(e);
      const tag = (t: string) => msg.includes(t) || Object.values(data).includes(t);
      const missing = Array.isArray(data.missing) ? (data.missing as string[]) : [];
      if (code === 'bad_input' && (missing.length || tag('ako_incomplete'))) {
        note = aw('ako.missing', { list: missing.map((d) => aw(k('ako.doc.' + d))).join(', ') });
      } else if (code === 'bad_input' && tag('ako_slot_needed')) note = aw('ako.needSlot');
      else if (code === 'bad_input' && tag('phone')) { bad.phone = 'ako.err.phone'; note = aw('ako.err.phone'); }
      else if (code === 'bad_input' && tag('email')) { bad.email = 'ako.err.email'; note = aw('ako.err.email'); }
      else if (code === 'bad_input') note = aw('ako.needName');
      else note = aw(errKey(e));
    } finally { busy = false; }
  }
</script>

<div class="send">
  <h1 class="a-h1">{aw('ako.contactsTitle')}</h1>

  <form class="form" novalidate onsubmit={(e) => e.preventDefault()} onfocusout={() => void save()}>
    <Field label={aw('ako.name')} bind:value={name} autocomplete="name" enterkeyhint="next" maxlength={120} />
    <Field label={aw('ako.phone')} bind:value={phone} type="tel" inputmode="tel" autocomplete="tel" enterkeyhint="next" maxlength={32}
      error={bad.phone ? aw(bad.phone) : undefined} />
    <Field label={aw('ako.email')} bind:value={email} type="email" inputmode="email" autocomplete="email" enterkeyhint="done" maxlength={160}
      error={bad.email ? aw(bad.email) : undefined} />
  </form>

  <h2 class="a-sec">{aw('ako.summary')}</h2>
  <dl class="a-card sum">
    <div class="r"><dt class="a-sub">{aw('ako.step.program')}</dt><dd>{title}</dd></div>
    <div class="r"><dt class="a-sub">{aw('ako.step.docs')}</dt><dd>{awn('ako.docsN', docs)}</dd></div>
    {#if program?.interview}
      <div class="r">
        <dt class="a-sub">{aw('ako.step.slot')}</dt>
        {#if view.slot}
          <dd><span class="cap">{weekday(view.slot.at)}, {dayMonth(view.slot.at)}</span><span class="big">{time(view.slot.at)}</span>
            <span class="a-sub">{aw('ako.almaty')}</span></dd>
        {:else}<dd class="no">{aw('ako.noTime')}</dd>{/if}
      </div>
    {/if}
  </dl>

  <div class="a-bar bar">
    {#if note}<p class="a-note bad" role="alert">{note}</p>{/if}
    <Button size="l" full loading={busy} label={busy ? aw('ako.sending') : undefined} onclick={send}>{aw('ako.send')}</Button>
  </div>
</div>

<style>
  .form { display: flex; flex-direction: column; gap: var(--s-4); margin-top: var(--s-6); }
  /* the app's Field, a step larger for this audience */
  .form :global(.lb) { font-size: var(--fs-body); color: var(--text-2); }
  .form :global(.box) { min-height: 56px; }
  .form :global(.err) { font-size: var(--fs-body); }

  .sum { margin: 0; padding: var(--s-2) var(--s-5); }
  .r { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-4); padding: var(--s-4) 0; }
  .r + .r { box-shadow: inset 0 0.5px 0 var(--separator); }
  dt { flex: none; }
  dd { margin: 0; min-width: 0; display: flex; flex-direction: column; align-items: flex-end; gap: 2px; text-align: right;
    font: 600 var(--fs-row)/1.3 var(--font-text); letter-spacing: -0.012em; }
  .cap::first-letter { text-transform: uppercase; }
  .big { font: 700 var(--fs-t3)/1.15 var(--font-display); font-variant-numeric: tabular-nums; }
  .no { color: var(--text-3); font-weight: 500; }

  /* the bar sits inside the step, which has its own bottom padding: take it back so it rests where Ako's does */
  .bar { margin-top: var(--s-4); margin-bottom: calc(-1 * var(--s-6)); }
</style>
