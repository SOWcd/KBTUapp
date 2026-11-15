<script lang="ts">
  // The app's own block, last on Profile (owner, Nov 15: only these): its channel, the bugs-and-ideas group, GitHub and
  // the creator's contact. One group of rows like every other on the page: a label, a grey value, an arrow out.
  // The voluntary support page and the main admin are not here: Settings has the first, Admin knows the second.
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { writeOwner, OWNER } from '../../lib/feedback';
  import { session } from '../../lib/state/session.svelte';

  // the app's own Telegram: news in the channel, talk in the topics group (BUGS / IDEAS / QUESTIONS)
  const TG_NEWS = 'https://t.me/KBTUappNews', TG_TALK = 'https://t.me/KBTUappTop', CODE = 'https://github.com/SOWcd/KBTUapp';
  // the creator as the server names him (his face and name); a guest or an old server: the @ alone
  const creator = $derived(session.support.find((p) => p.founder));
  const go = (url: string) => { haptic.tap(); openLink(url); };
</script>

<div class="appc" data-away><!-- data-away: it leaves while Me's settings are open -->
  <Group caption="KBTU App">
    <Row icon={Megaphone} title={t('app.channel')} value={t('app.channelSub')} accessory="external" onclick={() => go(TG_NEWS)} />
    <Row icon={MessagesSquare} title={t('app.group')} value={t('app.groupSub')} accessory="external" onclick={() => go(TG_TALK)} />
    <Row icon={GitHubMark} title="GitHub" value={t('app.codeSub')} accessory="external" onclick={() => go(CODE)} />
    <!-- a tap opens his Telegram with a draft that says it's from the app -->
    {#if creator}
      <Row title={creator.realName ?? creator.name} subtitle="{t('app.creator')} · @{creator.username}" accessory="external"
        onclick={() => go(`https://t.me/${creator.username}?text=${encodeURIComponent(t('fb.draft'))}`)}>{#snippet lead()}<Avatar person={creator} size={40} tappable={false} />{/snippet}</Row>
    {:else}
      <Row icon={TelegramMark} title="@{OWNER}" value={t('app.creator')} accessory="external" onclick={() => { haptic.tap(); writeOwner(); }} />
    {/if}
  </Group>
</div>

<style>
  .appc { margin-top: var(--s-3); } /* a captioned section: a step further from the group above */
</style>
