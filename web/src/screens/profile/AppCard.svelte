<script lang="ts">
  // The app itself (mockup v24: three tiles, small actions): its channel, its group, the open code (owner, Oct 17), and
  // a word straight to the creator (owner, Oct 5). At the bottom of Me (owner, Oct 25: not on Settings).
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

<!-- v25 (owner, Oct 25: "make the last two blocks beautiful"): a coloured orb per tile instead of grey boxes with three
     lines each; the tile is the button, so no "Subscribe / Join / Look" under it -->
<div class="appc surface">
  <div class="ap-h"><span class="mk"><KbtuMark size={22} /></span><span><b>KBTU App</b><i class="sub">{t('fb.text')}</i></span></div>
  <div class="ap-t">
    <button class="apt" style="--c:#2AABEE" onclick={() => openLink(TG_NEWS)}><span class="orb"><Megaphone size={21} /></span><b>{t('app.channel')}</b><small>{t('app.channelSub')}</small></button>
    <button class="apt" style="--c:#8B5CF6" onclick={() => openLink(TG_TALK)}><span class="orb"><UsersRound size={21} /></span><b>{t('app.group')}</b><small>{t('app.groupSub')}</small></button>
    <button class="apt" style="--c:#8E9BB5" onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}><span class="orb"><GitHubMark size={21} /></span><b>GitHub</b><small>{t('app.codeSub')}</small></button>
  </div>
  <!-- a word straight to the creator: its own long pill, his @username on it (owner, Oct 21) -->
  <button class="write" onclick={writeOwner}><span class="tg"><TelegramMark size={16} /></span><span class="wl">{t('fb.write')}</span><b>@{OWNER}</b></button>
</div>

<style>
  .sub { display: block; margin-top: 3px; font: 500 12.5px/1.3 var(--font-text); font-style: normal; color: var(--text-3); }
  .appc { display: flex; flex-direction: column; gap: 14px; padding: 16px; border-radius: var(--r-l); }
  .ap-h { display: flex; gap: 12px; align-items: center; }
  .ap-h b { font: 700 var(--fs-card)/1.2 var(--font-text); }
  .mk { flex: none; display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: 13px; color: #fff; background: linear-gradient(135deg, #2A4FD6, #5B2BC0); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 8px 18px -8px #5B2BC0; }
  .ap-t { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .apt { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 14px 6px 12px; border-radius: 18px; text-align: center;
    background: color-mix(in srgb, var(--c) 9%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--c) 18%, transparent); }
  .orb { display: flex; align-items: center; justify-content: center; width: 46px; height: 46px; margin-bottom: 8px; border-radius: 50%; color: #fff;
    background: radial-gradient(circle at 32% 28%, color-mix(in srgb, var(--c) 55%, #fff), var(--c) 62%, color-mix(in srgb, var(--c) 70%, #000));
    box-shadow: 0 8px 18px -6px color-mix(in srgb, var(--c) 75%, transparent), inset 0 1px 0 rgba(255, 255, 255, 0.35); }
  .apt b { font: 650 var(--fs-body)/1.15 var(--font-text); color: var(--text); }
  .apt small { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .write { position: relative; isolation: isolate; overflow: hidden; display: flex; align-items: center; gap: 10px; height: 50px; padding: 0 16px 0 7px; border-radius: var(--r-full);
    background: color-mix(in srgb, #2AABEE 12%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, #2AABEE 24%, transparent); color: #2AABEE; }
  .tg { display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 50%; color: #fff; background: linear-gradient(160deg, #3FB7F2, #1E8FD1); box-shadow: 0 6px 14px -6px #2AABEE; }
  .wl { flex: 1; text-align: left; font: 650 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .write b { font: 650 var(--fs-sub)/1 var(--font-text); color: #2AABEE; }
  .write:active, .apt:active { transform: scale(0.97); }
  :global(:root[data-theme='light']) .write b { color: #0F6E9F; } /* 4.9:1 on the tint */
</style>
