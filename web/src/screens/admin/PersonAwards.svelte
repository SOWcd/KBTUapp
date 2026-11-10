<script lang="ts">
  // One person's manual awards as chips (Admin → a person; owner, Nov 3: giving was "very inconvenient"): ui/Chip, a
  // held one selected with its medal in colour, the rest greyed. A tap gives at once (the bot sends them the award's
  // card; a toast says so); a held one is taken back behind a confirm. Bug hunter adds up: one more, or all of it back.
  // A badge is one chip, its held variants in the label; a tap opens its variants (owner, Nov 3: never a chip per
  // variant). The creator's own two show for the creator alone (the server refuses the rest).
  //   person  whose;  has  their awards when the caller has them already (the search's rows), else they load here
  import { api, ApiErr, type GrantItem, type PersonRef } from '../../lib/api';
  import { MANUAL, addsUp, codesOf, manualMedal, manualName, manualTitle, type Manual } from '../../lib/awards';
  import { say } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { menu } from '../../ui/menu';
  import Chip from '../../ui/Chip.svelte';
  import Medal from '../../ui/Medal.svelte';

  type Code = GrantItem['code'];
  let { person, has: given }: { person: PersonRef; has?: Code[] } = $props();

  const shown = $derived(MANUAL.filter((a) => !a.creator || !!session.me?.founder));
  let mine = $state<Code[] | null>(null);
  const held = $derived(mine ?? given ?? null);
  $effect(() => {
    const id = person.id; // another person in the same card: theirs, from scratch
    mine = null;
    if (!given) api.awardsOf(id).then((r) => { if (id === person.id) mine = r.has; }).catch(() => (mine = []));
  });
  const set = (codes: Code[]) => (mine = MANUAL.flatMap(codesOf).filter((c) => codes.includes(c)));

  function give(code: Code, org?: number) {
    const was = held ?? [];
    set([...was, code]); // the chip answers in the same frame
    haptic.tap();
    api.giveGrant(person.id, code, org).then(() => { haptic.ok(); say(t('aw.given', { award: manualName(code) }), 'party_popper_3d'); }).catch((e) => { set(was); haptic.error(); say(e instanceof ApiErr && e.code === 'conflict' ? t('give.already') : t('common.error'), 'pleading_face_3d'); });
  }
  async function take(code: Code) {
    if (!(await sheets.ask({ title: t('adm.takeBackAsk', { award: manualName(code), name: person.name }), ok: t('adm.takeBack'), cancel: t('common.cancel'), danger: true }))) return;
    const was = held ?? [];
    set(was.filter((c) => c !== code));
    api.takeBackGrant(person.id, code).then((r) => { mine = r.has; haptic.soft(); say(t('adm.takenBack'), 'waving_hand_3d_default'); })
      .catch(() => { set(was); haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
  function tap(a: Manual, e: MouseEvent) {
    if (a.variants) {
      // a badge: each variant, held ones checked (a tap on one takes it back, behind the confirm)
      menu(e.currentTarget as Element, a.variants.map((v) => ({ label: manualName(v.code, true), checked: !!held?.includes(v.code),
        onselect: () => (held?.includes(v.code) ? take(v.code) : give(v.code)) })));
      return;
    }
    const code = a.code as Code;
    if (code === 'club_founder' && !held?.includes(code)) {
      // its club first: an official one or one at the Ascent's top (the server checks the same)
      const clubs = [...data.orgs, ...data.small].filter((o) => o.kind === 'club' && (o.official || o.top)).sort((x, y) => x.name.localeCompare(y.name));
      if (!clubs.length) { say(t('aw.noClub'), 'pleading_face_3d'); return; }
      menu(e.currentTarget as Element, clubs.map((o) => ({ label: o.name, onselect: () => give(code, o.id) })));
      return;
    }
    if (!held?.includes(code)) give(code);
    else if (addsUp(code)) menu(e.currentTarget as Element, [
      { label: t('aw.oneMore'), onselect: () => give(code) },
      { label: t('adm.takeBack'), destructive: true, onselect: () => take(code) },
    ]);
    else take(code);
  }
</script>

<div class="chips">
  {#each shown as a (a.code)}
    {@const mineV = codesOf(a).filter((c) => held?.includes(c))}
    {@const on = mineV.length > 0}
    <Chip selected={on} onclick={(e) => held && tap(a, e)}>
      <span class="md"><Medal a={manualMedal(a.code, a.variants?.find((v) => v.code === mineV[0])?.emoji ?? a.emoji, on)} size={24} /></span>
      {manualTitle(a)}{#if a.variants && on}<span class="v">{mineV.map((c) => manualName(c, true)).join(', ')}</span>{/if}
    </Chip>
  {/each}
</div>

<style>
  .chips { display: flex; flex-wrap: wrap; gap: var(--s-2); padding: 4px 0; } /* 4 px: the 44 px hit areas stay whole */
  .chips :global(.fc) { max-width: 100%; padding-left: 6px; }
  .md { display: inline-flex; transition: opacity var(--t-base), filter var(--t-base); }
  .v { font-weight: 450; opacity: 0.8; }
  .v::before { content: '· '; }
</style>
