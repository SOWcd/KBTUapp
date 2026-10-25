<script lang="ts">
  // The app itself (mockup v24: three tiles, small actions): its channel, its group, the open code (owner, Oct 17), and
  // a word straight to the creator (owner, Oct 5). At the bottom of Me (owner, Oct 25: not on Settings).
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { openLink } from '../../lib/tg';
  import { writeOwner, OWNER } from '../../lib/feedback';

  // the app's own Telegram (owner, Oct 5): news in the channel, talk in the topics group (BUGS / IDEAS / QUESTIONS)
  const TG_NEWS = 'https://t.me/KBTUappNews', TG_TALK = 'https://t.me/KBTUappTop';
</script>

<!-- v25 (owner, Oct 25): the tiles read childish and the "found a bug" line went: three plain rows like Settings', each
     with its brand's small solid tile, then the pill to the creator -->
<div class="appc surface">
  <div class="ap-h"><span class="mk"><KbtuMark size={20} /></span><b>KBTU App</b></div>
  <button class="r" onclick={() => openLink(TG_NEWS)}><span class="ic" style="--c:#2AABEE"><Megaphone size={17} /></span>
    <span class="lb">{t('app.channel')}<i>{t('app.channelSub')}</i></span><ArrowUpRight size={16} /></button>
  <button class="r" onclick={() => openLink(TG_TALK)}><span class="ic" style="--c:#7C5CFF"><UsersRound size={17} /></span>
    <span class="lb">{t('app.group')}<i>{t('app.groupSub')}</i></span><ArrowUpRight size={16} /></button>
  <button class="r" onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}><span class="ic" style="--c:#24292F"><GitHubMark size={17} /></span>
    <span class="lb">GitHub<i>{t('app.codeSub')}</i></span><ArrowUpRight size={16} /></button>
  <!-- a word straight to the creator: its own long pill, his @username on it (owner, Oct 21) -->
  <button class="write" onclick={writeOwner}><TelegramMark size={17} /><span class="wl">{t('fb.write')}</span><b>@{OWNER}</b></button>
</div>

<style>
  .appc { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .ap-h { display: flex; gap: 10px; align-items: center; padding: 14px 16px 10px; }
  .ap-h b { font: 700 var(--fs-card)/1.2 var(--font-text); }
  .mk { flex: none; display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 10px; color: #fff; background: linear-gradient(135deg, #2A4FD6, #5B2BC0); }
  .r { display: flex; align-items: center; gap: 12px; min-height: 54px; padding: 0 16px; text-align: left; color: var(--text-3); box-shadow: inset 0 1px 0 var(--line); }
  .r:active { background: var(--surface-2); }
  .ic { flex: none; display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 10px; color: #fff; background: var(--c); }
  .lb { flex: 1; min-width: 0; font: 600 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .lb i { display: block; margin-top: 2px; font: 500 var(--fs-cap)/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .write { display: flex; align-items: center; gap: 10px; height: 46px; margin: 4px 12px 12px; padding: 0 16px; border-radius: var(--r-full);
    background: color-mix(in srgb, #2AABEE 14%, transparent); color: #2AABEE; }
  .wl { flex: 1; text-align: left; font: 650 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .write b { font: 650 var(--fs-sub)/1 var(--font-text); }
  .write:active { transform: scale(0.98); }
  :global(:root[data-theme='light']) .write { color: #0F6E9F; } /* 4.9:1 on the tint */
</style>
