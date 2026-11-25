<script lang="ts">
  // "Made together": one page that says the app is built and supported by many students, by the kind of what they
  // gave. The creator, modestly; then Code (the Team first), Ideas and finds (the idea's author first), Support (the
  // sponsors who agreed to be named, biggest first as the server orders them; the total only with its own yes).
  // A person with lines of both kinds stands in both sections, each with its own lines.
  // A name and a face unless that person hid them (server credits.py); a hidden person's line goes in its section's
  // last row, "Students": no face, nothing to tap, nothing that ties two such lines together. No account yet: the
  // name the team gave, with initials. A pull request's lines stand under its GitHub login, its row opens the profile
  // there; a named person known there too has the login as a link under their lines.
  // The numbers count lines, never people: nameless lines say nothing of how many people they are.
  // Both lists come with the app (data.credits, data.sponsors): the page never waits.
  //   at   'support': it opens at the Support section (the `sponsors` link, the donate page's row)
  import UsersRound from '@lucide/svelte/icons/users-round';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import Bug from '@lucide/svelte/icons/bug';
  import Award from '@lucide/svelte/icons/award';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import type { CreditItem, CreditPerson, PersonRef } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { data, loadCredits } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { lineOf } from '../../lib/credits';
  import { sponsorMedal, tierLabel } from '../../lib/awards';
  import { CODE } from '../../lib/feedback';
  import { session } from '../../lib/state/session.svelte';
  import Pane from '../../ui/Pane.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Medal from '../../ui/Medal.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';

  let { overlay, at }: { overlay: Overlay; at?: 'support' } = $props();
  const c = $derived(data.credits);
  // the app's copy in the same frame, then the server's word: someone may have taken their name back since (a read
  // this session made seconds ago, the bot's link, is that word)
  void loadCredits(5000);
  const open = (p: PersonRef) => { haptic.tap(); sheets.person(p.id); };
  const github = (login: string) => { haptic.tap(); openLink(`https://github.com/${login}`); };
  // his Telegram with the app's draft
  const tgOf = $derived(session.support.find((x) => x.founder)?.username);
  const realOf = (p: PersonRef) => p.realName ?? p.name;

  type Entry = CreditPerson & { role?: string };
  const lists = $derived.by(() => {
    const code: Entry[] = [], ideas: Entry[] = [], anonCode: CreditItem[] = [], anonIdeas: CreditItem[] = [];
    if (!c) return null;
    // role: the Team's label (always in Code) or the idea's author's (always first in Ideas and finds)
    const put = (r: CreditPerson, role?: string, home?: 'code' | 'ideas') => {
      const mine = r.items.filter((i) => i.kind === 'code'), rest = r.items.filter((i) => i.kind !== 'code');
      if (!r.person && !r.gh && !r.name && !home) { anonCode.push(...mine); anonIdeas.push(...rest); return; }
      const inCode = mine.length > 0 || home === 'code';
      if (inCode) code.push({ ...r, role: home === 'code' ? role : undefined, items: mine });
      // the medal's line once: with the code if they stand there
      if (rest.length || !inCode) ideas[home === 'ideas' ? 'unshift' : 'push']({ ...r, role: home === 'ideas' ? role : undefined, honor: r.honor && !inCode, items: rest });
    };
    for (const r of c.team) put(r, t('cr.team'), 'code');
    for (const r of c.people) put(r);
    if (c.idea) put(c.idea, t('cr.idea'), 'ideas');
    const n = (rows: Entry[], anon: CreditItem[]) => rows.reduce((s, r) => s + r.items.length, anon.length);
    return { code, ideas, anonCode, anonIdeas, codeN: n(code, anonCode), ideasN: n(ideas, anonIdeas) };
  });

  // the `sponsors` link: as the Support section is drawn (the lists above it already are), it stands under the
  // capsule. The pane's own scrollTop, never scrollIntoView: the pane is still sliding in from the right
  function jump(el: HTMLElement) {
    const sc = at === 'support' && el.closest('.scroll');
    if (sc) sc.scrollTop += el.getBoundingClientRect().top - sc.getBoundingClientRect().top - parseFloat(getComputedStyle(sc).paddingTop);
  }
</script>

{#snippet lines(items: CreditItem[], marks: boolean)}
  {#each items as i, n (n)}
    {@const K = i.kind === 'find' ? Bug : Lightbulb}
    <span class="ln">{#if marks}<span class="ki"><K size={14} /></span>{/if}<span>{lineOf(i)}</span></span>
  {/each}
{/snippet}

<!-- a row a person (or a GitHub login, or the nameless "Students"): who, then their lines of this section's kind -->
{#snippet who(e: Entry, marks: boolean)}
  {@const p = e.person}
  {@const login = e.gh}
  {@const go = p ? () => open(p) : login ? () => github(login) : undefined}
  {#snippet inner()}
      <span class="av">
        {#if p}<Avatar person={p} size={40} tappable={false} />
        {:else if e.name}<Avatar person={{ name: e.name }} size={40} tappable={false} />
        {:else if login}<span class="ic"><GitHubMark size={22} /></span>
        {:else}<span class="ic"><UsersRound size={20} /></span>{/if}
      </span>
      <span class="bd">
        <span class="tx">
          <b class="nm">{p ? (e.role ? realOf(p) : p.name) : e.name || login || t(e.role ? 'cr.student' : 'cr.students')}</b>
          {#if e.role}<span class="rl">{e.role}</span>{/if}
          {#if e.honor}<span class="ln"><span class="ki"><Award size={14} /></span><span>{t('ach.honor.name')}</span></span>{/if}
          {@render lines(e.items, marks)}
        </span>
        {#if p}<span class="mk"><ChevronRight size={18} /></span>{:else if login}<span class="mk"><ArrowUpRight size={18} /></span>{/if}
      </span>
  {/snippet}
  <div class="it kb-row">
    {#if go}<button class="main tap" onclick={go}>{@render inner()}</button>{:else}<div class="main">{@render inner()}</div>{/if}
    <!-- their GitHub too: a link of its own under their lines -->
    {#if p && login}<button class="gl press" onclick={() => github(login)}><GitHubMark size={15} /><span>{login}</span><ArrowUpRight size={14} /></button>{/if}
  </div>
{/snippet}

<Pane {overlay} title={t('cr.title')} icon={UsersRound} glow>
  <div class="mt">
    <p class="lead">{t('cr.lead')}</p>
    {#if !c || !lists}
      <Skeleton n={6} />
    {:else}
      <!-- I hid: my lines are here, my name isn't; showing it again one tap away (the sheet: what everyone would see) -->
      {#if c.mine && c.mine.consent === false}
        <div class="up" style:--d="0"><Group footnote={t('cr.meT')}>
          <Row title={t('cr.meShow')} tone="action" accessory="chevron" onclick={() => { haptic.tap(); sheets.creditAsk(); }} />
        </Group></div>
      {/if}
      {#if c.founder}
        {@const p = c.founder}
        <div class="up" style:--d="0"><Group>
          <Row title={realOf(p)} subtitle={t('cr.founder')} accessory="chevron" onclick={() => open(p)}>
            {#snippet lead()}<Avatar person={p} size={40} tappable={false} />{/snippet}
          </Row>
          {#if tgOf}<Row icon={TelegramMark} title={`@${tgOf}`} accessory="external" onclick={() => { haptic.tap(); openLink(`https://t.me/${tgOf}?text=${encodeURIComponent(t('fb.draft'))}`); }} />{/if}
        </Group></div>
      {/if}

      <div class="up" style:--d="1"><Group caption={t('cr.n.code')} note={lists.codeN ? String(lists.codeN) : undefined}>
        {#each lists.code as e, i (i)}{@render who(e, false)}{/each}
        {#if lists.anonCode.length}{@render who({ person: null, items: lists.anonCode }, false)}{/if}
        <Row icon={GitHubMark} title={t('cr.code')} accessory="external" onclick={() => { haptic.tap(); openLink(CODE); }} />
      </Group></div>

      {#if lists.ideas.length || lists.anonIdeas.length}
        <div class="up" style:--d="2"><Group caption={t('cr.list')} note={lists.ideasN ? String(lists.ideasN) : undefined}>
          {#each lists.ideas as e, i (i)}{@render who(e, true)}{/each}
          {#if lists.anonIdeas.length}{@render who({ person: null, items: lists.anonIdeas }, true)}{/if}
        </Group></div>
      {/if}

      <!-- only who agreed to be named (sp1), each with their medal; the total only with its own yes (sa1). The server
           orders it: tier, then the shown totals, so a place never hints at an amount nobody agreed to show -->
      {#if data.sponsors?.length || session.donate}
        <div use:jump><div class="up" style:--d="3">
          <Group caption={t('cr.support')} note={data.sponsors?.length ? String(data.sponsors.length) : undefined} footnote={t('sp.listHint')}>
            {#each data.sponsors ?? [] as p, i (i)}
              <Row title={p.name} subtitle={`${t('ach.sponsor.name')} · ${tierLabel(p.tier, 3)}`} value={p.amount ? money(p.amount) : undefined} whole>
                {#snippet lead()}<Medal a={sponsorMedal(p.tier)} size={40} />{/snippet}
              </Row>
            {/each}
            {#if data.sponsors && !data.sponsors.length}<Row title={t('sp.empty')} />{/if}
            {#if session.donate}<Row icon={HandHeart} title={t('set.donate')} tone="action" accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('donate'); }} />{/if}
          </Group>
        </div></div>
      {/if}
    {/if}
  </div>
</Pane>

<style>
  .mt { display: flex; flex-direction: column; gap: var(--s-8); }
  /* the one line under the title: closer to it than the sections are to each other */
  .lead { margin: calc(-1 * var(--s-2)) var(--s-1) calc(-1 * var(--s-2)); font: 450 var(--fs-row)/1.35 var(--font-text); letter-spacing: -0.01em; color: var(--text-2); }

  /* a person's row: Row's measures (16 in, 12 to the text, the line from the text), grown to hold their lines */
  .it { display: flex; flex-direction: column; }
  .main { display: flex; align-items: flex-start; gap: var(--s-3); width: 100%; padding-left: var(--s-4); text-align: left; color: var(--text); }
  .tap { transition: background-color var(--t-fast); }
  .tap:active { background: var(--fill); transform: none; opacity: 1; }
  @media (hover: hover) { .tap:hover { background: var(--fill); } }
  .av { flex: none; display: inline-flex; margin-top: var(--s-3); }
  .ic { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 50%; background: var(--fill); color: var(--text-2); }
  .bd { position: relative; flex: 1; min-width: 0; min-height: 64px; display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-4) var(--s-3) 0; }
  :global(.kb-row) + .it .bd::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 0.5px; background: var(--separator); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .nm { font: 600 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.01em; overflow-wrap: anywhere; }
  .rl { font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--accent-text); }
  .ln { display: flex; gap: 6px; font: 450 var(--fs-body)/1.35 var(--font-text); letter-spacing: -0.008em; color: var(--text-2); overflow-wrap: anywhere; }
  .ki { flex: none; display: inline-flex; align-items: center; height: 1.35em; color: var(--text-3); }
  .mk { flex: none; display: inline-flex; margin-right: -4px; color: var(--text-3); opacity: 0.6; }
  /* under the lines, from the text's edge; 44 to the finger */
  .gl { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; min-height: 44px; margin: calc(-1 * var(--s-3)) 0 0 calc(var(--s-4) + 40px + var(--s-3)); padding-right: var(--s-4);
    font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }

  /* the open: the blocks rise from just below, one after another. Once, nothing loops; none when the phone asks for
     less motion. The Support section's own box (use:jump) stays still: it is what the jump measures */
  .up { animation: up 700ms var(--ease-spring) calc(var(--d) * 70ms + 60ms) both; }
  @keyframes up { from { opacity: 0; transform: translateY(12px); } }
  :global(html.lowfx) .up { animation: none; }
  @media (prefers-reduced-motion: reduce) { .up { animation: none; } }
</style>
