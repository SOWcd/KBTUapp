<script lang="ts">
  // The organisation's medallion in the profile card's top right corner, where the QR was (owner, Nov 2: the QR lives on
  // the full-screen badge, MyQr): the club's logo, the school's shield, the KBTU mark, the creator's seal for SOWER,
  // set in a rim in the look's own metal (its colours, lib/awards.ts lookVars), a light catching it as the phone tilts.
  // Round 5 (owner, Nov 2): the organisation's own avatar, as the app shows it everywhere else, when it has one; our drawn
  // mark (LookMark) where it is clearly better this small, or the club has no logo: StudEx's arrow (their logo is a
  // wordmark), Cheerleading's panther (their round badge's ring of text is mush at 48 px), Moments' aperture (a wordmark
  // the strip already says), Faces' wordmark cropped tight on its black (their avatar's white margin wastes the face),
  // Shade's brush on their cream (their official logo is mostly empty cream at this size). Round 5b (owner, back to round
  // 4): every school's big shield on its colours, Crystal's big diamond, ArtHouse's red mark; AIChE's drawn benzene ring
  // (aiche-medal.svg), Choice's logo cut square on its navy. Round 6 (owner): StudEx's and Moments' official logos, bundled
  // (their wordmarks trimmed onto their own ground, .claude/reports/club-lanyards/src/prod-logos), not our drawn marks.
  // Round 7 (owner): Shade's own avatar (their prod upload), not our brush. Knights' official logo (.claude/reports/club-lanyards/knights-official.png) on white in a blue steel rim.
  import { clubLook, isSchool, type Look } from '../lib/awards';
  import LookMark from './LookMark.svelte';
  import Founder from './Founder.svelte';
  import aicheMedal from '../assets/lanyards/aiche-medal.svg?url';
  import studexLogo from '../assets/lanyards/studex-logo.webp';
  import momentsLogo from '../assets/lanyards/moments-logo.webp';
  import shadeLogo from '../assets/lanyards/shade-logo.webp'; // round 7: their prod avatar, trimmed a little onto its cream
  import knightsLogo from '../assets/lanyards/knights-logo.webp'; // round 7: their official logo (knight, building, ball) on white

  let { look, logo = null }: { look: Look; logo?: string | null } = $props();
  const DRAWN: Look[] = ['cheer', 'moments', 'faces', 'aichekbtu', 'crystalkbtu', 'arthousekbtu', 'choice'];
  // the official logos we ship: this file whatever the org's avatar is
  const OFFICIAL: Partial<Record<Look, string>> = { studex: studexLogo, moments: momentsLogo, knights: knightsLogo, shadekbtu: shadeLogo };
  const own = $derived(logo && !DRAWN.includes(look) && !isSchool(look) ? logo : null);
</script>

<span class="medal {look}" class:club={!!clubLook(look)} aria-hidden="true">
  <span class="face">{#if look === 'sower'}<Founder size={44} />{:else if look === 'aichekbtu'}<img src={aicheMedal} alt="" draggable="false" />{:else if OFFICIAL[look]}<img src={OFFICIAL[look]} alt="" draggable="false" />{:else if own}<img src={own} alt="" draggable="false" />{:else}<LookMark {look} />{/if}</span>
  <i class="catch"></i>
</span>

<style>
  /* a minted plate: a bevelled metal rim, the mark set into it, a soft drop onto the card */
  /* round 5: a finer rim (2 px, was 3) and the face's corner concentric with it */
  .medal { position: relative; display: block; width: 100%; height: 100%; padding: 2px; border-radius: var(--r-m);
    background: var(--rim, linear-gradient(145deg, rgb(255, 255, 255), rgb(176, 184, 202) 42%, rgb(244, 246, 251) 62%, rgb(140, 150, 172)));
    box-shadow: 0 12px 20px -10px rgba(0, 0, 0, 0.7), 0 2px 5px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.9), inset 0 -1px 1px rgba(0, 0, 0, 0.25); }
  .face { position: relative; display: block; width: 100%; height: 100%; overflow: hidden; border-radius: var(--r-s); background: white; }
  /* the inner shadow over the face, the logo's too: set into the rim, not pasted on it */
  .face::after { content: ''; position: absolute; inset: 0; border-radius: inherit; box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.4), inset 0 0 0 0.5px rgba(0, 0, 0, 0.18); pointer-events: none; }
  .face > img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .face :global(.appmark) { border-radius: var(--r-s); box-shadow: none; }
  .face :global(.appmark img) { width: 80%; height: 80%; }
  /* the light: one band sliding with the tilt across the rim and the face (the strip's mechanism; still at rest) */
  .catch { position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    background: linear-gradient(115deg, transparent 38%, rgba(255, 255, 255, 0.3) 50%, transparent 62%) calc(12% + var(--gx, 0) * 130%) 0 / 260% 100% no-repeat,
      radial-gradient(120% 70% at 30% 0%, rgba(255, 255, 255, 0.22), transparent 60%); }
  /* each look's metal: Cheer's gold, Knights' blue steel, the clubs' and schools' own two strap colours with a light edge */
  .cheer { --rim: linear-gradient(145deg, rgb(255, 238, 190), rgb(196, 154, 64) 45%, rgb(236, 204, 128) 62%, rgb(150, 112, 40)); }
  .knights { --rim: linear-gradient(145deg, rgb(255, 255, 255), rgb(120, 158, 228) 45%, rgb(236, 243, 255) 62%, rgb(28, 66, 150)); } /* round 7: their blue steel */
  .studex { --rim: linear-gradient(145deg, rgb(255, 255, 255), rgb(214, 38, 27) 45%, rgb(255, 210, 200) 62%, rgb(23, 48, 100)); }
  .moments { --rim: linear-gradient(145deg, rgb(246, 231, 214), rgb(196, 109, 71) 45%, rgb(242, 222, 200) 62%, rgb(110, 51, 34)); }
  .faces { --rim: linear-gradient(145deg, rgb(110, 123, 255), rgb(192, 75, 255) 40%, rgb(255, 79, 154) 70%, rgb(255, 164, 61)); }
  .club { --rim: linear-gradient(145deg, rgba(255, 255, 255, 0.95), var(--s2) 42%, var(--h1) 62%, var(--s1)); }
  /* the creator's seal is round: its own rim */
  .sower { padding: 0; border-radius: 50%; background: none; box-shadow: 0 12px 20px -10px rgba(0, 0, 0, 0.8); }
  .sower .face { display: flex; align-items: center; justify-content: center; border-radius: 50%; background: none; }
  .sower .face::after { content: none; }
  .sower .catch { border-radius: 50%; }
</style>
