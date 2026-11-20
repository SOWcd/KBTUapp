<script lang="ts">
  // "People of the app", in the pitch's manner (black, hairlines, a quiet label over one big thing per block): what
  // shipped in three numbers, the creator, the idea's author, then every line, newest first by the day it shipped:
  // never by amount. A name and a face only after that person's own yes (server credits.py); without it a line is a
  // row of its own signed "Student" beside its kind: no face, no icon, nothing to tap, nothing that ties two such
  // lines together. A pull request's lines stand under its GitHub login, the row opens the profile there.
  // The numbers count lines, never people: nameless lines say nothing of how many people they are.
  // The list comes with the app (data.credits): the page never waits.
  import UsersRound from '@lucide/svelte/icons/users-round';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import type { CreditKind, PersonRef } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { data, loadCredits } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { largeTitle } from '../../ui/title';
  import Pane from '../../ui/Pane.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import CreditLines from '../../ui/CreditLines.svelte';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import { CODE } from '../../lib/feedback';
  import { session } from '../../lib/state/session.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const c = $derived(data.credits);
  // the app's copy in the same frame, then the server's word: someone may have taken their name back since (a read
  // this session made seconds ago, the bot's link, is that word)
  void loadCredits(5000);
  const open = (p: PersonRef) => { haptic.tap(); sheets.person(p.id); };
  // his Telegram with the app's draft
  const tgOf = $derived(session.support.find((x) => x.founder)?.username);
  const realOf = (p: PersonRef) => p.realName ?? p.name;
  const KINDS: CreditKind[] = ['idea', 'find', 'code'];
  const stats = $derived.by(() => {
    const n: Record<CreditKind, number> = { idea: 0, find: 0, code: 0 };
    for (const r of c ? [...c.people, ...(c.idea ? [c.idea] : [])] : []) for (const i of r.items) n[i.kind]++;
    return KINDS.filter((k) => n[k]).map((k) => ({ k, n: n[k] }));
  });
</script>

<!-- a word rising from under its own baseline, as the pitch's headings do -->
{#snippet rise(text: string, at = 0)}{#each text.split(' ') as w, i (i)}<span class="w"><span style:--i={at + i}>{w}</span></span>{/each}{/snippet}

<Pane {overlay} title={t('cr.title')} icon={UsersRound} bare opal>
  <div class="ppl">
    <h1 class="lbl ttl" use:largeTitle={(g) => (overlay.quiet = !g)}>{t('cr.title')}</h1>
    {#if !c}
      <div class="wait"><Skeleton n={6} /></div>
    {:else}
      {#if stats.length}
        <div class="stats">
          {#each stats as s, i (s.k)}
            <div class="stat"><span class="lbl">{t(`cr.n.${s.k}`)}</span><b class="num">{@render rise(String(s.n), i)}</b></div>
          {/each}
        </div>
      {/if}
      {#if c.founder}
        {@const p = c.founder}
        <div class="blk first up" style:--d="1">
          <button class="star press" onclick={() => open(p)}>
            <span class="txt"><span class="lbl">{t('cr.founder')}</span><b class="nm big">{@render rise(realOf(p), 3)}</b></span>
            <Avatar person={p} size={64} tappable={false} />
          </button>
          {#if tgOf}<button class="link press" onclick={() => { haptic.tap(); openLink(`https://t.me/${tgOf}?text=${encodeURIComponent(t('fb.draft'))}`); }}><span>@{tgOf}</span><ArrowUpRight size={15} /></button>{/if}
        </div>
      {/if}
      {#if c.idea}
        {@const p = c.idea.person}
        <div class="blk up" style:--d="2">
          <svelte:element this={p ? 'button' : 'div'} class="star" class:press={!!p} onclick={p ? () => open(p) : undefined} role={p ? undefined : 'group'}>
            <span class="txt"><span class="lbl">{t('cr.idea')}</span><b class="nm">{p ? realOf(p) : t('cr.student')}</b></span>
            {#if p}<Avatar person={p} size={44} tappable={false} />{/if}
          </svelte:element>
          {#if c.idea.items.length}<span class="more"><CreditLines items={c.idea.items} under="idea" /></span>{/if}
        </div>
      {/if}
      {#if c.people.length}
        <div class="list up" style:--d="3"><Group caption={t('cr.list')}>
          {#each c.people as row, i (i)}
            {@const p = row.person}
            {@const gh = !p && row.gh}
            <svelte:element this={p || gh ? 'button' : 'div'} class="who" class:tap={!!(p || gh)} role={p || gh ? undefined : 'group'}
              onclick={p ? () => open(p) : gh ? () => { haptic.tap(); openLink(`https://github.com/${gh}`); } : undefined}>
              {#if p}
                <span class="hd"><Avatar person={p} size={28} tappable={false} /><b class="wn">{p.name}</b><span class="mk"><ChevronRight size={18} /></span></span>
              {:else if gh}
                <span class="hd"><span class="gh"><GitHubMark size={22} /></span><b class="wn">{gh}</b><span class="mk"><ArrowUpRight size={18} /></span></span>
              {/if}
              <CreditLines items={row.items} by={p || gh ? undefined : t('cr.student')} />
            </svelte:element>
          {/each}
        </Group></div>
      {/if}
      <button class="link code press up" style:--d="4" onclick={() => { haptic.tap(); openLink(CODE); }}>
        <GitHubMark size={16} /><span>{t('cr.code')}</span><ArrowUpRight size={15} />
      </button>
    {/if}
  </div>
</Pane>

<style>
  .ppl { display: flex; flex-direction: column; padding: 0 var(--s-1); }
  /* the one quiet label: over the numbers, the creator, the idea */
  .lbl { font: 600 var(--fs-micro)/1.3 var(--font-text); letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-3); }
  .ttl { margin: var(--s-5) 0 0; }

  .stats { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: var(--s-4); margin-top: var(--s-8); }
  .stat { display: flex; flex-direction: column; gap: var(--s-2); padding-top: var(--s-3); border-top: 1px solid var(--separator); }
  .num { font: 700 var(--fs-title)/1 var(--font-display); letter-spacing: -0.035em; font-variant-numeric: tabular-nums; }

  .blk { display: flex; flex-direction: column; align-items: flex-start; margin-top: var(--s-8); padding-top: var(--s-4); border-top: 1px solid var(--separator); }
  .blk.first { margin-top: var(--s-10); }
  .star { display: flex; align-items: center; justify-content: space-between; gap: var(--s-4); width: 100%; color: var(--text); text-align: left; }
  .txt { min-width: 0; display: flex; flex-direction: column; gap: 6px; }
  .nm { font: 700 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.02em; overflow-wrap: anywhere; }
  .nm.big { font: 700 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .more { margin-top: var(--s-3); }
  .link { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; margin-bottom: calc(-1 * var(--s-3)); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .code { align-self: center; margin: var(--s-8) 0 0; padding: 0 var(--s-3); }

  .list { margin: var(--s-10) calc(-1 * var(--s-1)) 0; }
  .who { position: relative; display: flex; flex-direction: column; gap: var(--s-3); width: 100%; padding: 14px var(--s-4); text-align: left; color: var(--text); }
  .tap { transition: background-color var(--t-fast); }
  .tap:active { background: var(--fill); transform: none; opacity: 1; }
  @media (hover: hover) { .tap:hover { background: var(--fill); } }
  .who + .who::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .hd { display: flex; align-items: center; gap: 10px; }
  .gh { flex: none; display: inline-grid; place-items: center; width: 28px; height: 28px; }
  .wn { flex: 1; min-width: 0; font: 600 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.01em; overflow-wrap: anywhere; }
  .mk { flex: none; display: inline-flex; margin-right: -4px; color: var(--text-3); opacity: 0.6; }
  .wait { margin-top: var(--s-10); }

  /* the open: a number and the creator's name rise from under their baseline, the blocks follow from just below.
     Once, slow, nothing loops; none at all when the phone asks for less motion */
  .w { display: inline-block; overflow: hidden; vertical-align: top; padding: 0 0.04em 0.12em; margin: 0 -0.04em -0.12em; }
  .w + .w { margin-left: 0.22em; }
  .w > span { display: inline-block; animation: word 1000ms var(--ease-spring) calc(var(--i) * 70ms + 80ms) both; }
  .up { animation: up 900ms var(--ease-spring) calc(var(--d) * 90ms + 80ms) both; }
  @keyframes word { from { transform: translateY(110%); } }
  @keyframes up { from { opacity: 0; transform: translateY(16px); } }
  :global(html.lowfx) .w > span, :global(html.lowfx) .up { animation: none; }
  @media (prefers-reduced-motion: reduce) { .w > span, .up { animation: none; } }
</style>
