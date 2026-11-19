<script lang="ts">
  // "People of the app" (owner, Nov 18): the creator, the idea's author, then everyone whose idea, find or code shipped,
  // newest first by the day it shipped: never by amount. A little like film credits (a centred top, air), scrolled by
  // hand. A name and a face only after that person's own yes (server credits.py); without it the app signs the lines
  // "Student", each line a row of its own: a plain row, nothing to tap; a pull request's lines stand under its GitHub
  // login, the row opens the profile there. The list comes with the app (data.credits): the page never waits.
  import UsersRound from '@lucide/svelte/icons/users-round';
  import UserRound from '@lucide/svelte/icons/user-round';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import type { PersonRef } from '../../lib/api';
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
  // his Telegram with the app's draft: the creator's row on Profile opened it before it became the way here
  const tgOf = $derived(session.support.find((x) => x.founder)?.username);
  const realOf = (p: PersonRef) => p.realName ?? p.name;
</script>

{#snippet anon(size: number)}<span class="anon" style:width="{size}px" style:height="{size}px"><UserRound size={Math.round(size * 0.5)} strokeWidth={1.8} /></span>{/snippet}

<Pane {overlay} title={t('cr.title')} icon={UsersRound} bare>
  <div class="ppl">
    <h1 class="ttl" use:largeTitle={(g) => (overlay.quiet = !g)}>{t('cr.title')}</h1>
    {#if !c}
      <div class="wait"><Skeleton n={6} /></div>
    {:else}
      {#if c.founder}
        {@const p = c.founder}
        <button class="star press" onclick={() => open(p)}>
          <Avatar person={p} size={112} tappable={false} />
          <span class="role">{t('cr.founder')}</span>
          <b class="nm big">{realOf(p)}</b>
        </button>
        {#if tgOf}<button class="code write press" onclick={() => { haptic.tap(); openLink(`https://t.me/${tgOf}?text=${encodeURIComponent(t('fb.draft'))}`); }}><span>@{tgOf}</span><ArrowUpRight size={15} /></button>{/if}
      {/if}
      {#if c.idea}
        {@const p = c.idea.person}
        <svelte:element this={p ? 'button' : 'div'} class="star second" class:press={!!p} onclick={p ? () => open(p) : undefined} role={p ? undefined : 'group'}>
          {#if p}<Avatar person={p} size={76} tappable={false} />{:else}{@render anon(76)}{/if}
          <span class="role">{t('cr.idea')}</span>
          <b class="nm">{p ? realOf(p) : t('cr.student')}</b>
          {#if c.idea.items.length}<span class="more"><CreditLines items={c.idea.items} center /></span>{/if}
        </svelte:element>
      {/if}
      {#if c.people.length}
        <div class="list"><Group caption={t('cr.list')}>
          {#each c.people as row, i (i)}
            {@const p = row.person}
            {@const gh = !p && row.gh}
            <svelte:element this={p || gh ? 'button' : 'div'} class="who" class:tap={!!(p || gh)} role={p || gh ? undefined : 'group'}
              onclick={p ? () => open(p) : gh ? () => { haptic.tap(); openLink(`https://github.com/${gh}`); } : undefined}>
              <span class="face">{#if p}<Avatar person={p} size={40} tappable={false} />{:else if gh}<span class="anon gh"><GitHubMark size={22} /></span>{:else}{@render anon(40)}{/if}</span>
              <span class="body">
                <span class="hd"><b class="wn" class:dim={!p && !gh}>{p ? p.name : gh || t('cr.student')}</b>{#if p}<span class="mk"><ChevronRight size={18} /></span>{:else if gh}<span class="mk"><ArrowUpRight size={18} /></span>{/if}</span>
                <CreditLines items={row.items} />
              </span>
            </svelte:element>
          {/each}
        </Group></div>
      {/if}
      <button class="code press" onclick={() => { haptic.tap(); openLink(CODE); }}>
        <GitHubMark size={16} /><span>{t('cr.code')}</span><ArrowUpRight size={15} />
      </button>
    {/if}
  </div>
</Pane>

<style>
  .ppl { display: flex; flex-direction: column; align-items: center; }
  .ttl { margin: var(--s-6) 0 0; font: 800 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.03em; text-align: center; text-wrap: balance; }
  .star { display: flex; flex-direction: column; align-items: center; max-width: 100%; margin-top: var(--s-10); padding: 0 var(--s-2); color: var(--text); text-align: center; }
  .star.second { margin-top: var(--s-8); }
  .role { margin-top: var(--s-4); font: 600 var(--fs-cap)/1.2 var(--font-text); letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-3); }
  .second .role { margin-top: var(--s-3); }
  .nm { margin-top: 4px; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; overflow-wrap: anywhere; }
  .nm.big { font: 800 var(--fs-t1)/1.15 var(--font-display); letter-spacing: -0.03em; }
  .more { margin-top: var(--s-2); }
  .anon.gh { width: 40px; height: 40px; color: var(--text); }
  .anon { flex: none; display: inline-grid; place-items: center; border-radius: 50%; background: var(--fill); color: var(--text-3); }
  .list { align-self: stretch; margin-top: var(--s-10); }
  .who { position: relative; display: flex; align-items: flex-start; gap: var(--s-3); width: 100%; padding-left: var(--s-4); text-align: left; color: var(--text); }
  .tap { transition: background-color var(--t-fast); }
  .tap:active { background: var(--fill); transform: none; opacity: 1; }
  @media (hover: hover) { .tap:hover { background: var(--fill); } }
  .face { flex: none; display: inline-flex; padding-top: var(--s-3); }
  .body { position: relative; flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; padding: var(--s-3) var(--s-4) var(--s-3) 0; }
  .hd { display: flex; align-items: center; gap: var(--s-2); min-height: 40px; margin-bottom: -6px; } /* the name level with the face, the row's end mark on its line */
  /* the line between people starts where the name does, as in every Group */
  .who + .who .body::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 0.5px; background: var(--separator); }
  .wn { flex: 1; min-width: 0; font: 600 var(--fs-row)/1.25 var(--font-text); overflow-wrap: anywhere; }
  .wn.dim { color: var(--text-2); font-weight: 450; }
  .mk { flex: none; display: inline-flex; margin-right: -4px; color: var(--text-3); opacity: 0.6; }
  .code { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; margin-top: var(--s-8); padding: 0 var(--s-3);
    font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .code.write { margin-top: 2px; min-height: 36px; }
  .wait { align-self: stretch; margin-top: var(--s-10); }
</style>
