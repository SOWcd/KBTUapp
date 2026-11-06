<script lang="ts">
  // The app's links and people, at the bottom of Profile (owner, Nov 6: the best of three takes: Astra's glass card and
  // tiles with a line under each, colour-coded icons in tinted squares, Telegram in its own round mark).
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Avatar from '../../ui/Avatar.svelte';
  import { writeOwner, OWNER } from '../../lib/feedback';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';

  // the app's own Telegram: news in the channel, talk in the topics group (BUGS / IDEAS / QUESTIONS)
  const TG_NEWS = 'https://t.me/KBTUappNews', TG_TALK = 'https://t.me/KBTUappTop';
  const support = $derived(session.support);
  const write = (u: string) => { haptic.tap(); openLink(`https://t.me/${u}?text=${encodeURIComponent(t('fb.draft'))}`); };
</script>

<div class="appc surface" data-away><!-- data-away: it leaves while Me's settings are open -->
  <div class="ap-h"><span class="mk"><KbtuMark size={22} /></span><h2>KBTU App</h2></div>
  <div class="ap-t">
    <button class="apt" onclick={() => openLink(TG_NEWS)}><span class="ic news"><Megaphone size={20} strokeWidth={2} /></span>
      <b>{t('app.channel')}</b><small>{t('app.channelSub')}</small><ArrowUpRight class="go" size={12} aria-hidden="true" /></button>
    <button class="apt" onclick={() => openLink(TG_TALK)}><span class="ic talk"><MessagesSquare size={20} strokeWidth={2} /></span>
      <b>{t('app.group')}</b><small>{t('app.groupSub')}</small><ArrowUpRight class="go" size={12} aria-hidden="true" /></button>
  </div>
  <!-- in-app, so a row with a chevron, apart from the two tiles that leave for Telegram (owner, Nov 6) -->
  {#if session.donate}
    <button class="give-r" onclick={() => { haptic.tap(); sheets.settings('donate'); }}><span class="ic give"><HandHeart size={20} strokeWidth={2} /></span>
      <span class="wt"><b>{t('app.donateRow')}</b><small>{t('don.bank')}</small></span><ChevronRight class="chev" size={18} aria-hidden="true" /></button>
  {:else}
    <button class="give-r" onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}><span class="ic give"><GitHubMark size={22} /></span>
      <span class="wt"><b>GitHub</b><small>{t('app.codeSub')}</small></span><ArrowUpRight class="chev" size={16} aria-hidden="true" /></button>
  {/if}
  {#if support.length}
    <!-- one way to us: two faces, each a tap to their Telegram with a draft that says it's from the app -->
    <h3 class="sp-h">{t('app.support')}</h3>
    <div class="sp">
      {#each support as p (p.id)}
        <button class="who" onclick={() => write(p.username)}>
          <Avatar person={p} size={40} tappable={false} />
          <span class="wt"><b class="ellipsis">{p.realName ?? p.name}</b><small>{p.founder ? t('app.creator') : t('app.mainAdmin')}</small></span>
          <span class="tg"><TelegramMark size={15} /></span>
        </button>
      {/each}
    </div>
  {:else}
    <button class="write" onclick={writeOwner}><TelegramMark size={17} /><span class="wl">{t('fb.write')}</span><b>@{OWNER}</b></button>
  {/if}
</div>

<style>
  .appc { padding: var(--s-5) var(--s-4) var(--s-2); border-radius: var(--r-l);
    background: linear-gradient(145deg, var(--lg-sheen), transparent 45%), var(--surface);
    box-shadow: inset 0 1px 0 var(--line-2), inset 0 0 0 1px var(--line); }
  .ap-h { display: flex; align-items: center; gap: var(--s-3); margin-bottom: var(--s-5); }
  .ap-h h2 { font: 700 var(--fs-t3)/1.2 var(--font-text); letter-spacing: -0.025em; }
  .mk { flex: none; display: grid; place-items: center; width: var(--ctl-s); height: var(--ctl-s);
    border-radius: var(--r-s); color: var(--on-accent); background: var(--grad-accent);
    box-shadow: inset 0 1px 0 var(--glass-sheen); }
  .ap-t { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-2); }
  /* A quiet bevel gives the actions depth without competing with the faces below. */
  .apt { position: relative; display: flex; flex-direction: column; align-items: flex-start; min-width: 0;
    min-height: 116px; padding: var(--s-4) var(--s-3); border-radius: var(--r-m); text-align: left;
    background: linear-gradient(155deg, var(--lens-top), transparent 65%), var(--surface-2);
    box-shadow: inset 0 1px 0 var(--line-2), inset 0 0 0 1px var(--line); }
  .ic { display: grid; place-items: center; width: 40px; height: 40px; margin-bottom: var(--s-3); border-radius: var(--r-s); }
  .news { color: #2AABEE; background: rgba(42, 171, 238, 0.16); }
  .talk { color: #9B87FF; background: rgba(124, 92, 255, 0.18); }
  .give { color: var(--accent-text); background: var(--accent-soft); }
  .tg { flex: none; display: grid; place-items: center; width: 32px; height: 32px; border-radius: var(--r-full); color: #2AABEE; background: rgba(42, 171, 238, 0.14); }
  .apt b { font: 600 var(--fs-body)/1.3 var(--font-text); letter-spacing: -0.02em; color: var(--text); }
  .apt small { margin-top: var(--s-1); font: 450 var(--fs-cap)/1.4 var(--font-text); color: var(--text-2); overflow-wrap: anywhere; }
  .apt :global(.go) { position: absolute; top: var(--s-3); right: var(--s-2); color: var(--text-3); }
  .give-r { position: relative; display: flex; align-items: center; gap: var(--s-3); width: 100%; margin-top: var(--s-2);
    padding: var(--s-3); border-radius: var(--r-m); text-align: left;
    background: linear-gradient(155deg, var(--lens-top), transparent 65%), var(--surface-2);
    box-shadow: inset 0 1px 0 var(--line-2), inset 0 0 0 1px var(--line); }
  .give-r .ic { margin-bottom: 0; }
  .give-r :global(.chev) { flex: none; color: var(--text-3); }
  .sp-h { margin: var(--s-6) 0 var(--s-2); font: 600 var(--fs-sub)/1.4 var(--font-text); color: var(--text-2); }
  .sp { display: flex; flex-direction: column; }
  .who { position: relative; display: flex; align-items: center; gap: var(--s-3); width: 100%; min-width: 0;
    min-height: var(--row-h2); padding: var(--s-3) 0; border-radius: var(--r-xs); color: var(--accent-text); text-align: left; }
  .who + .who::before { content: ''; position: absolute; top: 0; left: calc(var(--s-10) + var(--s-3)); right: 0;
    height: 1px; background: var(--line); }
  .wt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--s-1); }
  .wt b { font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text); }
  .wt small { font: 450 var(--fs-cap)/1.3 var(--font-text); color: var(--text-2); }
  .write { display: flex; align-items: center; gap: var(--s-3); min-height: var(--ctl-l); margin-top: var(--s-4);
    padding: var(--s-3) 0; border-radius: var(--r-xs); color: var(--accent-text); }
  .wl { flex: 1; text-align: left; font: 600 var(--fs-sub)/1.4 var(--font-text); color: var(--text); }
  .write b { font: 600 var(--fs-sub)/1.4 var(--font-text); }
  .apt, .give-r, .who, .write { transition: transform var(--t-base) var(--ease), opacity var(--t-fast) var(--ease); }
  .apt:active, .give-r:active, .who:active, .write:active { transform: scale(0.98); opacity: 0.75; transition-duration: var(--t-fast); }
  @media (hover: hover) {
    .apt:hover, .give-r:hover { background-color: var(--fill-2); }
    .who:hover, .write:hover { background-color: var(--surface-2); }
  }
  @media (prefers-reduced-motion: reduce) { .apt:active, .give-r:active, .who:active, .write:active { transform: none; } }
  @media (max-width: 359px) {
    .appc { padding-inline: var(--s-3); }
    .apt { padding-inline: var(--s-2); }
  }
</style>
