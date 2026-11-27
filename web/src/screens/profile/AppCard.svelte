<script lang="ts">
  // The app's own block, last on Profile (only these): its channel, the bugs-and-ideas group, GitHub and
  // the people who made it (the creator and the idea's author; a tap: Made together, People.svelte; his contact is there). One group of rows like every other on the page: a label, a grey value, an arrow out.
  // On Android, first: the Google Play app's row until the person has opened it (the tester steps' page).
  // Helping (an offer) and supporting (the donate page) are one row, HelpSheet (the sponsors are on Made together); the main admin is not here, Admin knows him.
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import MessageCircleWarning from '@lucide/svelte/icons/message-circle-warning';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import PlayMark from '../../ui/PlayMark.svelte';
  import { count } from '../../lib/stats';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import type { PersonRef } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { openPlayPage } from '../../lib/androidTest';
  import { haptic, inPlayApp, onAndroid, openLink } from '../../lib/tg';
  import { CODE, TALK } from '../../lib/feedback';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';

  // the app's own Telegram: news in the channel, talk in the topics group (BUGS / IDEAS / QUESTIONS)
  const TG_NEWS = 'https://t.me/KBTUappNews';
  // the creator as the server names him (his face and name) and the idea's author once she said yes (data.credits)
  const creator = $derived(data.credits?.founder ?? session.support.find((p) => p.founder));
  const muse = $derived(data.credits?.idea?.person ?? null);
  const plain = (p: PersonRef) => ({ id: p.id, name: p.name, avatar: p.avatar }); // two faces close together: without their seals (the screen has them)
  const nameOf = (p: PersonRef) => p.realName ?? p.name;
  const names = $derived(creator && muse ? t('cr.two', { a: nameOf(creator), b: nameOf(muse) }) : creator ? nameOf(creator) : muse ? nameOf(muse) : undefined);
  const go = (url: string) => { haptic.tap(); openLink(url); };
  const helpRow = () => { haptic.tap(); if (session.me?.student || !session.donate) sheets.helpUs(); else sheets.settings('donate'); };
  // the Android app's lasting way in (the entry sheet comes at most twice): on Android, until the person has opened
  // the installed app (here: inPlayApp; in Telegram: the account's androidApp); counted drawn once a launch, and tapped
  const play = $derived(onAndroid && !inPlayApp && !!session.me && !session.me.androidApp);
  $effect(() => { if (play && !drawn) { drawn = true; count('andr.row'); } });
  const playRow = () => { haptic.tap(); openPlayPage('andr.rowgo'); };
</script>

<script module lang="ts">
  let drawn = false; // once a launch, however often Profile is drawn
</script>

<div class="appc" data-away><!-- data-away: it leaves while Me's settings are open -->
  <Group caption="KBTU App">
    {#if play}<Row icon={PlayMark} title={t('andr.row')} value={t('andr.rowSub')} accessory="external" onclick={playRow} />{/if}
    <!-- the channel and the group only for who isn't in them yet (server logic/appchats.py: the bot hears joins and leaves) -->
    {#if !session.me?.inChannel}<Row icon={Megaphone} title={t('app.channel')} value={t('app.channelSub')} accessory="external" onclick={() => go(TG_NEWS)} />{/if}
    {#if !session.me?.inGroup}<Row icon={MessagesSquare} title={t('app.group')} value={t('app.groupSub')} accessory="external" onclick={() => go(TALK)} />{/if}
    <Row icon={GitHubMark} title="GitHub" value={t('app.codeSub')} accessory="external" onclick={() => go(CODE)} />
    <!-- students make the app: one row for every way to help (HelpSheet: an offer, and the donate page); a guest, who
         can't send an offer, goes straight to the donate page -->
    <Row icon={HeartHandshake} title={t('help.title')} value={t('help.rowSub')} accessory="chevron" onclick={helpRow} />
    <Row icon={MessageCircleWarning} title={t('fb.title')} value={t('fb.rowSub')} accessory="chevron" onclick={() => { haptic.tap(); sheets.feedback(); }} />
    <!-- who made it: the creator and the idea's author (named after her own yes), and the way to everyone else -->
    <Row title={t('cr.title')} subtitle={names} accessory="chevron" onclick={() => { haptic.tap(); sheets.credits(); }}>
      {#snippet lead()}<span class="two">{#if creator}<Avatar person={plain(creator)} size={36} tappable={false} />{/if}{#if muse}<span class="b"><Avatar person={plain(muse)} size={36} tappable={false} /></span>{/if}{#if !creator && !muse}<span class="none"><UsersRound size={20} /></span>{/if}</span>{/snippet}
    </Row>
  </Group>
</div>

<style>
  .appc { margin-top: var(--s-3); }
  .two { display: inline-flex; align-items: center; }
  .b { display: inline-flex; margin-left: -12px; border-radius: 50%; box-shadow: 0 0 0 2px var(--surface); }
  .none { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; background: var(--fill); color: var(--text-3); } /* a captioned section: a step further from the group above */
</style>
