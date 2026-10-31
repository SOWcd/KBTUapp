<script lang="ts">
  // The design system's lab (dev server only: `?lab`, main.ts): every ui/ component in every state on one page, inside
  // the real chrome (the capsule, the tab bar, the overlay stack, Telegram's Back), both themes and the three languages a
  // tap away. The words on the components are the app's own (t()), so their real lengths show at 320 px; the lab's
  // own labels are English, for the people building screens.
  import { onMount } from 'svelte';
  import FlaskConical from '@lucide/svelte/icons/flask-conical';
  import SunMoon from '@lucide/svelte/icons/sun-moon';
  import Languages from '@lucide/svelte/icons/languages';
  import Bell from '@lucide/svelte/icons/bell';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import Lock from '@lucide/svelte/icons/lock';
  import Share from '@lucide/svelte/icons/share';
  import Flag from '@lucide/svelte/icons/flag';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import Ticket from '@lucide/svelte/icons/ticket';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Plus from '@lucide/svelte/icons/plus';
  import Search from '@lucide/svelte/icons/search';
  import Inbox from '@lucide/svelte/icons/inbox';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import X from '@lucide/svelte/icons/x';
  import Camera from '@lucide/svelte/icons/camera';
  import Backpack from '@lucide/svelte/icons/backpack';
  import CircleHelp from '@lucide/svelte/icons/circle-help';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import Users from '@lucide/svelte/icons/users';
  import { ui, overlays, open, close, say, type Tab } from '../../lib/state/ui.svelte';
  import { backButton } from '../../lib/tg';
  import { t, i18n, setLang, loadLang, LANGS, LANG_FULL, money, type Lang } from '../../lib/i18n/index.svelte';
  import { theme, chooseTheme } from '../../lib/state/theme.svelte';
  import { sheets } from '../../lib/state/sheets';
  import Capsule from '../../ui/Capsule.svelte';
  import Nav from '../../ui/Nav.svelte';
  import Toast from '../../ui/Toast.svelte';
  import Ask from '../../ui/Ask.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Pane from '../../ui/Pane.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Toolbar from '../../ui/Toolbar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Card from '../../ui/Card.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Badge from '../../ui/Badge.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import Field from '../../ui/Field.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import Composer from '../../ui/Composer.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import { menu, type MenuItem } from '../../ui/menu';
  import { fitTitle } from '../../ui/title';

  // the chrome, the way App wires it: Telegram's Back and Escape close the top overlay; the capsule says the top one
  onMount(() => {
    backButton.onClick(() => close());
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape' && overlays.some((o) => !o.closing)) close(); };
    addEventListener('keydown', esc);
    return () => removeEventListener('keydown', esc);
  });
  $effect(() => { if (overlays.some((o) => !o.closing)) backButton.show(); else backButton.hide(); });
  const capOf = $derived([...overlays].reverse().find((o) => !o.closing && (o.title || o.quiet)));
  const TABS: Tab[] = ['afisha', 'forum', 'club', 'profile'];
  const LABEL: Record<Tab, () => string> = { afisha: () => t('tab.afisha'), forum: () => t('tab.forum'), club: () => t('page.clubs'), profile: () => t('tab.profile') };

  function lang(l: Lang) { void loadLang(l).then(() => setLang(l)); }
  const langItems = (): MenuItem[] => LANGS.map((l) => ({ label: LANG_FULL[l], checked: i18n.lang === l, instant: true, onselect: () => lang(l) }));
  const themeItems = (el: Element): MenuItem[] => (['dark', 'light'] as const).map((x) => ({ label: t(x === 'dark' ? 'theme.dark' : 'theme.light'), checked: theme.current === x, instant: true, onselect: () => chooseTheme(x, el) }));
  const postItems: MenuItem[] = [
    { label: t('event.share'), icon: Share, onselect: () => say(t('event.share')) },
    { label: t('cm.report'), icon: Flag, onselect: () => say(t('cm.report')) },
    { label: t('pd.del'), icon: Trash2, destructive: true, onselect: () => void sheets.ask({ title: t('pd.del'), ok: t('pd.del'), cancel: t('common.cancel'), danger: true }) },
  ];

  // states the page plays with
  let seg2 = $state<'a' | 'b'>('a'), seg3 = $state(1);
  let topic = $state('all');
  let q = $state(''), q2 = $state(t('clubs.search'));
  let name = $state(''), name2 = $state('Dana Seitova'), bad = $state('+7 707'), about = $state('');
  let draft = $state(''), draft2 = $state(''), anon = $state(false), sending = $state(false);
  let sw1 = $state(true), sw2 = $state(false), pick = $state<Lang>('ru'), folded = $state(true);
  let busy = $state(false), went = $state(false);
  const send = () => { sending = true; setTimeout(() => { sending = false; draft = ''; draft2 = ''; }, 900); };
  const me = { id: 1, name: 'Dana Seitova' };
  const ask = () => void sheets.ask({ title: t('event.cancelReg'), ok: t('event.cancelReg'), cancel: t('common.cancel'), danger: true });
  // Ask is the app's own: wired as App wires it
  sheets.ask = (q) => new Promise((done) => { open(Ask, { ...q, done }); });

  // short and tall: the design system's sheet (its title in its own header row, the capsule shows its icon); full: the old
  // way (the capsule says the title; no icon given, so the app's mark instead of the Sparkles that stood in before)
  const sheet = (kind: 'short' | 'tall' | 'full') => kind === 'full'
    ? open(Sheet, { title: t('page.awards'), full: true, children: longBody })
    : open(Sheet, { heading: kind === 'short' ? 'Board games night' : t('set.privacy'), icon: kind === 'short' ? Ticket : Lock, tall: kind === 'tall',
      actions: sheetTools, children: kind === 'short' ? shortBody : longBody, footer: sheetFoot });
  const pane = () => open(Pane, { title: t('me.notifications'), icon: Bell, children: paneBody });
</script>

{#snippet shortBody()}
  <p class="lead">Content-height sheet: one decision. The footer holds the one filled L button.</p>
  <Group><Row title={t('event.ticket')} value="18:30" dense /><Row title={t('pd.city')} value="Almaty" dense /></Group>
{/snippet}
{#snippet sheetTools()}<IconButton icon={Ellipsis} label="More" onclick={(e) => menu(e.currentTarget as Element, postItems)} />{/snippet}
{#snippet sheetFoot()}
  <div class="btns pair"><Button kind="gray" size="l" full onclick={() => close()}>{t('common.cancel')}</Button><Button size="l" full onclick={() => close()}>{t('common.save')}</Button></div>
{/snippet}
{#snippet longBody()}
  <p class="lead">A tall or full sheet: its content scrolls under the edge.</p>
  <div class="stack">
    {#each Array.from({ length: 4 }, (_, i) => i) as i (i)}
      <Group caption={'Group ' + (i + 1)}>
        <Row title={t('set.remind')} accessory="switch" checked={i % 2 === 0} />
        <Row title={t('set.newEvents')} accessory="chevron" onclick={() => {}} />
        <Row title={t('set.forum')} value={t('set.on')} accessory="chevron" onclick={() => {}} />
      </Group>
    {/each}
  </div>
{/snippet}
{#snippet paneBody()}
  <div class="stack">
    <Group footnote={t('set.always')}>
      <Row title={t('set.remind')} accessory="switch" checked={sw1} onchange={(v) => (sw1 = v)} />
      <Row title={t('set.newEvents')} accessory="switch" checked={sw2} onchange={(v) => (sw2 = v)} />
      <Row title={t('set.forum')} accessory="switch" checked />
    </Group>
  </div>
{/snippet}

<div class="lab scroll" data-page>
  <header class="head">
    <h1 class="fs-title">Lab</h1>
    <Toolbar items={[{ icon: SunMoon, label: 'Theme', onclick: (e) => chooseTheme(theme.current === 'dark' ? 'light' : 'dark', e.currentTarget as Element) },
      { icon: Languages, label: 'Language', onclick: (e) => menu(e.currentTarget as Element, langItems()) }]} />
  </header>

  <!-- ---- type ---- -->
  <h2 class="lh">Type</h2>
  <div class="card-ish type">
    <p class="fs-title" use:fitTitle>{t('set.privacy')}</p><i class="k">fs-title 34/800, use:fitTitle (down to 24: one word never breaks)</i>
    <p class="fs-t1">Dana Seitova</p><i class="k">fs-t1 28/700</i>
    <p class="fs-sec">{t('clubs.popular')}</p><i class="k">fs-sec 22/700</i>
    <p class="fs-t3 num">2 000 ₸</p><i class="k">fs-t3 20/700</i>
    <p class="fs-row">{t('set.remind')}</p><i class="k">fs-row 17/450: menu-like rows</i>
    <p class="fs-body">{t('event.cancelReg')} · {t('power.title')}</p><i class="k">fs-body 15/450: data rows, text</i>
    <p class="fs-sub">{t('set.always')}</p><i class="k">fs-sub 13/450: captions, footnotes</i>
    <p class="fs-cap">{t('event.youGo')}</p><i class="k">fs-cap 12/600</i>
    <p class="fs-micro">{t('tab.profile')}</p><i class="k">fs-micro 11/600</i>
  </div>

  <!-- ---- buttons ---- -->
  <h2 class="lh">Button</h2>
  {#each ['filled', 'tinted', 'gray', 'plain'] as const as k (k)}
    <i class="k">{k}: l / m / s · destructive · disabled</i>
    <div class="wrap">
      <Button kind={k} size="l">{t('common.save')}</Button><Button kind={k}>{t('event.ticket')}</Button><Button kind={k} size="s">{t('common.more')}</Button>
      <Button kind={k} destructive>{t('pd.del')}</Button><Button kind={k} disabled>{t('common.save')}</Button>
    </div>
  {/each}
  <i class="k">with an icon · loading · done · on (toggled) · full L</i>
  <div class="wrap">
    <Button>{#snippet icon()}<Ticket size={20} />{/snippet}{t('event.ticket')}</Button>
    <Button loading={busy} onclick={() => { busy = true; setTimeout(() => (busy = false), 1200); }}>{t('common.save')}</Button>
    <Button done={went} onclick={() => (went = !went)}>{went ? t('event.youGo') : t('event.go')}</Button>
    <Button kind="tinted" on>{t('event.youGo')}</Button>
  </div>
  <Button size="l" full>{t('event.goPrice', { price: money(2000) })}</Button>
  <i class="k">a long L label takes two lines at 320 · a footer pair (base.css .btns)</i>
  <Button size="l" full>{t('event.notify')}</Button>
  <div class="btns pair"><Button kind="gray" size="l" full>{t('common.cancel')}</Button><Button size="l" full destructive>{t('event.cancelReg')}</Button></div>
  <i class="k">old names, now aliases: primary · secondary · neutral · danger</i>
  <div class="wrap"><Button kind="primary">{t('event.go')}</Button><Button kind="secondary">{t('event.ticket')}</Button><Button kind="neutral">{t('common.more')}</Button><Button kind="danger">{t('pd.del')}</Button></div>
  <i class="k">over a poster: glass · onmedia (filled, white)</i>
  <div class="poster">
    <Emoji name="popcorn_3d" size={64} />
    <div class="wrap"><Button kind="glass">{#snippet icon()}<Bookmark size={20} />{/snippet}{t('event.save')}</Button><Button onmedia>{t('event.go')}</Button><IconButton kind="glass" icon={Share} label={t('event.share')} /></div>
  </div>

  <h2 class="lh">IconButton</h2>
  <i class="k">gray · tinted · filled · plain · glass · s 36 · l 50 · badge · on · disabled</i>
  <div class="wrap">
    <IconButton icon={Ellipsis} label="More" /><IconButton kind="tinted" icon={Plus} label="Add" /><IconButton kind="filled" icon={Search} label="Search" />
    <IconButton kind="plain" icon={X} label="Close" /><IconButton size="s" icon={Bell} label="Bell" /><IconButton size="l" icon={Bookmark} label="Save" />
    <IconButton icon={Bell} label="Bell" badge={3} /><IconButton icon={Bookmark} label="Saved" on /><IconButton icon={Camera} label="Camera" disabled />
  </div>
  <i class="k">beside a 50 footer button</i>
  <div class="foot-demo"><IconButton size="l" icon={Bookmark} label={t('event.save')} /><IconButton size="l" icon={Share} label={t('event.share')} /><Button size="l" full>{t('event.goPrice', { price: money(2000) })}</Button></div>

  <h2 class="lh">Toolbar</h2>
  <i class="k">1 · 2 · 3 tools (gray); glass when pinned over content; ⋯ opens a Menu</i>
  <div class="wrap">
    <Toolbar items={[{ icon: Ellipsis, label: 'More', onclick: (e) => menu(e.currentTarget as Element, postItems) }]} />
    <Toolbar items={[{ icon: Share, label: 'Share', onclick: () => {} }, { icon: Ellipsis, label: 'More', onclick: (e) => menu(e.currentTarget as Element, postItems) }]} />
    <Toolbar items={[{ icon: Search, label: 'Search', onclick: () => {} }, { icon: Bell, label: 'Bell', onclick: () => {}, badge: 2 }, { icon: Ellipsis, label: 'More', onclick: (e) => menu(e.currentTarget as Element, postItems) }]} />
  </div>
  <div class="poster short"><Toolbar glass items={[{ icon: Share, label: 'Share', onclick: () => {} }, { icon: Ellipsis, label: 'More', onclick: (e) => menu(e.currentTarget as Element, postItems) }]} /></div>

  <h2 class="lh">Menu</h2>
  <i class="k">picks with a check (instant: view transitions) · actions with icons, destructive last</i>
  <div class="wrap">
    <span id="lab-menu-lang"><Button kind="gray" onclick={(e) => menu(e.currentTarget as Element, langItems(), 'start')}>{LANG_FULL[i18n.lang]}</Button></span>
    <span id="lab-menu-post"><IconButton icon={Ellipsis} label="More" onclick={(e) => menu(e.currentTarget as Element, postItems)} /></span>
  </div>

  <!-- ---- lists ---- -->
  <h2 class="lh">Group · Row</h2>
  <div class="stack">
    <Group>
      <Row title="Dana Seitova" subtitle="24B100001 · SITE" lead={av} accessory="chevron" onclick={() => {}} />
    </Group>
    <Group>
      <Row icon={Languages} tile="gray" title={t('me.guestLang')} value={LANG_FULL[i18n.lang]} menu={langItems()} />
      <Row icon={SunMoon} tile="indigo" title={t('me.guestTheme')} value={t(theme.current === 'dark' ? 'theme.dark' : 'theme.light')} menu={themeItems(document.body)} />
    </Group>
    <Group>
      <Row icon={Bell} tile="red" title={t('me.notifications')} value="2/3" accessory="chevron" onclick={pane} />
      <Row icon={CalendarDays} tile="orange" title={t('set.calShort')} accessory="external" onclick={() => {}} />
      <Row icon={BatteryMedium} tile="green" title={t('power.title')} value={t('power.auto')} accessory="chevron" onclick={() => {}} />
      <Row icon={Users} tile="blue" title={t('page.friends')} detail={faces} count={2} accessory="chevron" onclick={() => {}} />
    </Group>
    <Group caption={t('me.guestLang')} footnote="A pick list: rows with a check (accessory check).">
      {#each LANGS as l (l)}<Row title={LANG_FULL[l]} accessory="check" checked={pick === l} onclick={() => (pick = l)} />{/each}
    </Group>
    <Group caption="switch · disclosure · trailing button · add">
      <Row title={t('set.remind')} accessory="switch" checked={sw1} onchange={(v) => (sw1 = v)} />
      <Row title={t('set.whoSees')} accessory="disclosure" open={!folded} onclick={() => (folded = !folded)} />
      {#if !folded}<EmptyState inline text={t('cm.empty')} />{/if}
      <Row title="Board games night" subtitle="Room 305 · 18:30" lead={emoji} trailing={rowBtn} />
      <Row tone="add" title={t('inv.title')} onclick={() => {}} />
    </Group>
    <Group caption="dense data rows (15/600)">
      <Row dense title="Linear Algebra" subtitle="09:00 – 09:50 · 305" value="2" />
      <Row dense title="Algorithms and Data Structures" subtitle="10:00 – 10:50 · 251" lead={avSmall} accessory="chevron" onclick={() => {}} />
    </Group>
    <Group><Row tone="action" title={t('set.calShort')} onclick={() => {}} /></Group>
    <Group><Row tone="destructive" title={t('sched.del')} onclick={ask} /></Group>
  </div>
  {#snippet av()}<Avatar person={me} size={54} tappable={false} />{/snippet}
  {#snippet avSmall()}<Avatar person={{ id: 2, name: 'Ali Nurlanov' }} size={32} tappable={false} />{/snippet}
  {#snippet emoji()}<Emoji name="popcorn_3d" size={32} />{/snippet}
  {#snippet faces()}<span class="faces"><Avatar person={{ id: 2, name: 'Ali N' }} size={24} tappable={false} /><Avatar person={{ id: 3, name: 'Bota A' }} size={24} tappable={false} /></span>{/snippet}
  {#snippet rowBtn()}<Button kind="gray" size="s">{t('event.go')}</Button>{/snippet}

  <h2 class="lh">Section · Card</h2>
  <Section title={t('clubs.popular')} count={12} onmore={() => {}}>
    <Card onclick={() => {}}>
      <div class="cardrow"><Emoji name="microphone_3d" size={44} /><div><p class="fs-row strong">Open Mic: stand-up and music</p><p class="fs-sub dim">18:30 · Atrium</p></div></div>
      <div class="tags"><Tag tone="accent">{t('event.youGo')}</Tag><Tag>{t('event.partner')}</Tag></div>
    </Card>
  </Section>
  <Section title="Long section title that wraps at 320" count={3} onmore={() => {}}><Card><p class="fs-body">A static card: no tap.</p></Card></Section>

  <h2 class="lh">Chip · Tag · Badge</h2>
  <i class="k">filter chips: selected is tinted (never solid ink); icons monochrome</i>
  <div class="chips hscroll">
    <Chip selected={topic === 'all'} onclick={() => (topic = 'all')}>{t('common.all')}</Chip>
    <Chip selected={topic === 'help'} icon={CircleHelp} onclick={() => (topic = 'help')}>{t('bd.topic.help')}</Chip>
    <Chip selected={topic === 'thing'} icon={Backpack} onclick={() => (topic = 'thing')}>{t('bd.topic.thing')}</Chip>
    <Chip selected={topic === 'go'} icon={MapPin} onclick={() => (topic = 'go')}>{t('bd.topic.go')}</Chip>
    <Chip selected={topic === 'talk'} icon={MessageCircle} onclick={() => (topic = 'talk')}>{t('bd.topic.talk')}</Chip>
  </div>
  <i class="k">tags (statuses, the old Chip's look) · badges</i>
  <div class="wrap">
    <Tag>{t('studio.draft')}</Tag><Tag tone="accent">{t('event.youGo')}</Tag><Tag tone="success">{t('event.live')}</Tag><Tag tone="warning">{t('event.firstYear')}</Tag>
    <Tag tone="danger">{t('event.cancelled')}</Tag><Badge n={1} /><Badge n={12} /><Badge n={120} />
  </div>

  <h2 class="lh">Segmented</h2>
  <div class="stack">
    <Segmented items={[{ value: 'a', label: t('clubs.myClub') }, { value: 'b', label: t('page.clubs') }]} bind:value={seg2} />
    <Segmented items={[{ value: 0, label: t('common.today') }, { value: 1, label: t('common.tomorrow') }, { value: 2, label: t('studio.draft') }]} bind:value={seg3} />
  </div>

  <h2 class="lh">Field · SearchField</h2>
  <div class="stack">
    <Field label={t('pd.city')} bind:value={name} placeholder="Almaty" />
    <Field label="Name" bind:value={name2} />
    <Field label={t('pd.phone')} bind:value={bad} type="tel" error={t('common.error')} />
    <Field label="About" bind:value={about} multiline placeholder={t('cm.ph')} />
    <SearchField bind:value={q} placeholder={t('clubs.search')} />
    <SearchField bind:value={q2} placeholder={t('clubs.search')} />
  </div>

  <h2 class="lh">EmptyState · Skeleton</h2>
  <div class="card-ish">
    <EmptyState icon={Inbox} title={t('news.emptyTitle')} text={t('cm.empty')} action={{ label: t('inv.title'), onclick: () => {} }} />
  </div>
  <div class="card-ish"><EmptyState icon={CircleCheck} tone="success" title={t('cm.empty')} /></div>
  <div class="card-ish"><EmptyState onretry={() => say(t('common.retry'))} text={t('common.offline')} /></div>
  <div class="stack"><Skeleton kind="rows" n={2} /><Skeleton kind="cards" n={1} /><Skeleton kind="lines" n={3} /></div>

  <h2 class="lh">Composer</h2>
  <div class="stack">
    <Composer bind:value={draft} placeholder={t('cm.ph')} onsend={send} {sending} />
    <span id="lab-composer-as"><Composer bind:value={draft2} placeholder={t(anon ? 'bd.anonPh' : 'bd.replyPh')} onsend={send} {sending} as={{ me, anon, onchange: (v) => (anon = v) }} /></span>
  </div>

  <h2 class="lh">Sheet · Pane · Ask · Toast</h2>
  <div class="wrap">
    <span id="lab-sheet-short"><Button kind="gray" onclick={() => sheet('short')}>Sheet</Button></span>
    <span id="lab-sheet-tall"><Button kind="gray" onclick={() => sheet('tall')}>Tall</Button></span>
    <span id="lab-sheet-full"><Button kind="gray" onclick={() => sheet('full')}>Full</Button></span>
    <span id="lab-pane"><Button kind="gray" onclick={pane}>Pane</Button></span>
    <span id="lab-ask"><Button kind="tinted" destructive onclick={ask}>Ask</Button></span>
    <Button kind="gray" onclick={() => say(t('cm.empty'), 'sparkles_3d')}>Toast</Button>
  </div>
  <div class="stack bottom">
    <Group caption="a row at the bottom: its menu flips up">
      <Row icon={Lock} tile="blue" title={t('set.privacy')} value={LANG_FULL[i18n.lang]} menu={langItems()} />
    </Group>
  </div>
  <div class="tail"></div>
</div>

<div class="topfade" aria-hidden="true"></div>
<div class="cap-theme {capOf?.theme ? `theme-${capOf.theme}` : ''}"><Capsule title={capOf ? (capOf.quiet || capOf.mark ? null : capOf.title) : 'Lab'} icon={capOf ? (capOf.quiet ? null : capOf.icon ?? KbtuMark) : FlaskConical} mark={!!capOf?.mark} /></div>
<Nav tabs={TABS} labels={TABS.map((k) => LABEL[k]())} dot={[false, true, false, false]} />
{#each overlays as o (o.id)}
  <o.component {...o.props} overlay={o} />
{/each}
<Toast />

<style>
  .cap-theme { display: contents; }
  .topfade { position: absolute; inset: 0; z-index: calc(var(--z-capsule) - 1); pointer-events: none; background: var(--bg);
    -webkit-mask-image: linear-gradient(black calc(var(--head-bottom) - 4px), transparent var(--page-top));
    mask-image: linear-gradient(black calc(var(--head-bottom) - 4px), transparent var(--page-top)); }
  .lab { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: var(--s-3); background: var(--bg); }
  .lab > :global(*) { flex-shrink: 0; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin: 6px 4px 0; }
  .lh { margin: var(--s-7) 4px 0; font: 700 var(--fs-sec)/1.18 var(--font-display); letter-spacing: -0.018em; }
  .k { display: block; margin: var(--s-2) 4px 0; font: 450 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-3); }
  .wrap { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2); }
  .stack { display: flex; flex-direction: column; gap: var(--gap-group); }
  .card-ish { padding: var(--s-4); border-radius: var(--r-l); background: var(--surface); }
  .type { display: flex; flex-direction: column; gap: 2px; }
  .type .k { margin: 0 0 var(--s-2); }
  .poster { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--s-5) var(--s-3); border-radius: var(--r-l);
    background: linear-gradient(160deg, var(--accent), var(--accent-2)); }
  .poster.short { align-items: flex-end; padding: var(--s-3); }
  .foot-demo { display: flex; align-items: center; gap: var(--s-2); }
  .pair { display: flex; gap: var(--s-2); }
  .lead { margin: 0 4px var(--s-4); font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text-2); }
  .faces { display: inline-flex; }
  .faces > :global(*) + :global(*) { margin-left: -8px; }
  .cardrow { display: flex; align-items: center; gap: var(--s-3); }
  .strong { font-weight: 600; }
  .tags { display: flex; gap: 6px; margin-top: var(--s-3); }
  .chips { gap: var(--s-2); padding: 4px 0; }
  .bottom { margin-top: var(--s-7); }
  .tail { flex: none; height: calc(var(--bottom) + 24px); }
</style>
