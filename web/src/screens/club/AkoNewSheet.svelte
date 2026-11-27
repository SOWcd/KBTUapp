<script lang="ts">
  import { akoTeam } from '../../lib/api/akoTeam';
  // After a consultation: program (one tap), name, phone, the page's language → a link. Then the same sheet becomes
  // "the link is ready": the link (shown once), WhatsApp as the main action, copy under it.
  import { ApiErr, type Id, type AkoDesk } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { i18n, t, LANG_FULL } from '../../lib/i18n/index.svelte';
  import { aw } from '../../lib/i18n/ako';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, org, desk, onchange }: { overlay: Overlay; org: Id; desk: AkoDesk; onchange?: () => void } = $props();

  const LANGS = (['ru', 'kk', 'en'] as const).map((l) => [l, LANG_FULL[l]] as const);
  type Lang = typeof LANGS[number][0];
  const programs = $derived([...desk.programs].sort((a, b) => Number(b.kind === 'degree') - Number(a.kind === 'degree')));

  let program = $state('');
  let name = $state('');
  let phone = $state('');
  let lang = $state<Lang>('ru');
  let err = $state({ program: '', name: '', phone: '' });
  let busy = $state(false);
  let token = $state('');

  /** WhatsApp's number: digits only, a local 8… or a bare ten digits become 7… */
  function digits(p: string): string {
    const d = p.replace(/\D/g, '');
    return d.length === 11 && d[0] === '8' ? '7' + d.slice(1) : d.length === 10 ? '7' + d : d;
  }
  const tag = (e: unknown) => (e instanceof ApiErr ? [e.message, (e as { field?: string }).field, (e as { detail?: string }).detail].join(' ') : '');

  const link = $derived(`${location.origin}/ako/${token}`);
  const picked = $derived(desk.programs.find((p) => p.key === program));

  async function make() {
    if (busy) return;
    const n = name.trim(), d = digits(phone);
    err = { program: program ? '' : aw('akd.needProgram'), name: n.length >= 2 ? '' : aw('akd.needName'), phone: d.length >= 11 && d.length <= 15 ? '' : aw('ako.err.phone') };
    if (err.program || err.name || err.phone) { haptic.warn(); return; }
    busy = true;
    try {
      token = (await akoTeam.akoNew(org, { program, name: n, phone: phone.trim(), lang })).token;
      haptic.ok();
      onchange?.();
    } catch (e) {
      haptic.error();
      if (tag(e).includes('phone')) err.phone = aw('ako.err.phone');
      else say(t('common.error'), 'warning_3d');
    } finally { busy = false; }
  }

  function whatsapp() {
    const text = aw('akd.waText', { name: name.trim(), program: picked?.info[lang].title ?? '', link });
    openLink(`https://wa.me/${digits(phone)}?text=${encodeURIComponent(text)}`);
  }
  async function copy() {
    try { await navigator.clipboard.writeText(link); haptic.ok(); say(aw('akd.copied')); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<Sheet {overlay} heading={aw(token ? 'akd.linkReady' : 'akd.new')}>
  {#if token}
    <div class="col in">
      <p class="sub">{name.trim()} · {picked?.info[i18n.lang].title}</p>
      <p class="link selectable">{link}</p>
      <p class="once">{aw('akd.linkOnce')}</p>
    </div>
  {:else}
    <div class="col">
      <div class="sec">
        <p class="lb">{aw('akd.program')}</p>
        <Group>
          {#each programs as p (p.key)}
            <Row dense title={p.info[i18n.lang].title} subtitle={p.info[i18n.lang].sub || undefined} accessory="check" checked={program === p.key}
              onclick={() => { haptic.select(); program = p.key; err.program = ''; }} />
          {/each}
        </Group>
        {#if err.program}<p class="bad">{err.program}</p>{/if}
      </div>
      <Field label={aw('akd.name')} bind:value={name} error={err.name || undefined} autocomplete="off" enterkeyhint="next" maxlength={120} />
      <Field label={aw('akd.phone')} bind:value={phone} error={err.phone || undefined} type="tel" inputmode="tel" placeholder="+7" autocomplete="off" enterkeyhint="done" maxlength={24} />
      <div class="sec">
        <p class="lb">{aw('akd.lang')}</p>
        <div class="chips" role="radiogroup" aria-label={aw('akd.lang')}>
          {#each LANGS as [v, label] (v)}
            <button class="chip" class:on={lang === v} role="radio" aria-checked={lang === v} onclick={() => { haptic.select(); lang = v; }}>{label}</button>
          {/each}
        </div>
      </div>
    </div>
  {/if}

  {#snippet footer()}
    {#if token}
      <div class="foot">
        <Button size="l" full lit onclick={whatsapp}>{aw('akd.sendWa')}</Button>
        <Button kind="secondary" size="l" full onclick={copy}>{aw('akd.copy')}</Button>
      </div>
    {:else}
      <Button size="l" full loading={busy} onclick={make}>{aw('akd.make')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--s-4); }
  .sec { display: flex; flex-direction: column; gap: var(--s-2); }
  .in { gap: var(--s-3); animation: in var(--t-base) var(--ease) both; }
  @keyframes in { from { opacity: 0; transform: translateY(6px); } }
  @media (prefers-reduced-motion: reduce) { .in { animation: none; } }
  .lb { padding: 0 var(--s-4); color: var(--text-3); font: 450 var(--fs-sub)/1.2 var(--font-text); }
  .bad { padding: 0 var(--s-4); color: var(--danger-text); font: 450 var(--fs-sub)/1.35 var(--font-text); }
  .sub { margin: calc(-1 * var(--s-2)) 2px var(--s-1); color: var(--text-3); font: 450 var(--fs-body)/1.35 var(--font-text); }
  .link { padding: var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 500 var(--fs-row)/1.35 var(--font-text); letter-spacing: -0.012em; overflow-wrap: anywhere; }
  .once { padding: 0 var(--s-4); color: var(--text-3); font: 450 var(--fs-sub)/1.4 var(--font-text); }
  .chips { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .chip { height: var(--ctl-s); padding: 0 var(--s-4); border-radius: var(--r-full); background: var(--fill); color: var(--text);
    font: 600 var(--fs-sub)/1 var(--font-text); transition: background-color var(--t-fast), color var(--t-fast); }
  .chip.on { background: var(--accent-soft); color: var(--accent-text); }
  .chip:active { transform: none; opacity: 0.7; }
  .foot { display: flex; flex-direction: column; gap: var(--s-2); }
</style>
