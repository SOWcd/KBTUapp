<script lang="ts">
  // The organisation's medallion in the profile card's top right corner, where the QR was (the QR lives on
  // the full-screen badge, MyQr): the club's logo, the school's shield, the KBTU mark, a white KBTU tile for SOWER,
  // set in a rim in the look's own metal (its colours, lib/awards.ts lookVars), a light catching it as the phone tilts.
  // The organisation's own avatar, as the app shows it everywhere else, when it has one; our drawn
  // mark (LookMark) where it is clearly better this small, or the club has no logo: StudEx's arrow (their logo is a
  // wordmark), Cheerleading's panther (their round badge's ring of text is mush at 48 px), Moments' aperture (a wordmark
  // the strip already says), Faces' wordmark cropped tight on its black (their avatar's white margin wastes the face),
  // Shade's brush on their cream (their official logo is mostly empty cream at this size). Every school's big shield on its colours, Crystal's big diamond, ArtHouse's red mark; AIChE's drawn benzene ring
  // (aiche-medal.svg), Choice's logo cut square on its navy. StudEx's and Moments' official logos, bundled
  // (their wordmarks trimmed onto their own ground, .claude/reports/club-lanyards/src/prod-logos), not our drawn marks.
  // Shade's own avatar (their prod upload), not our brush. Knights' official logo (.claude/reports/club-lanyards/knights-official.png) on white in a blue steel rim.
  import { ARCHIVE_LOOKS, clubLook, isSchool, type Look } from '../lib/awards';
  import LookMark from './LookMark.svelte';
  import KbtuMark from './KbtuMark.svelte';
  import aicheMedal from '../assets/lanyards/aiche-medal.svg?url';
  import studexLogo from '../assets/lanyards/studex-logo.webp';
  import momentsLogo from '../assets/lanyards/moments-logo.webp';
  import shadeLogo from '../assets/lanyards/shade-logo.webp'; // their prod avatar, trimmed a little onto its cream
  import knightsLogo from '../assets/lanyards/knights-logo.webp'; // their official logo (knight, building, ball) on white
  import oteLogo from '../assets/lanyards/ote-logo.webp'; // their wordmark on its blush, squared
  import magLogo from '../assets/lanyards/kbtumag-logo.webp'; // their wordmark on its cream, squared
  import cyberLogo from '../assets/lanyards/cyber-logo.webp'; // their badge on its black, squared
  import ddLogo from '../assets/lanyards/dd-logo.webp'; // their round logo on its black, squared
  import bhLogo from '../assets/lanyards/bh-logo.webp'; // The Bay Harbor Society's DEXTER on its black, squared
  import qolonerLogo from '../assets/lanyards/qoloner-logo.webp'; // Qoloner's frog in their ring on cream, redrawn (their round logo's lettering is mush at 48 px)

  // Cinema's avatar is an AI picture; our camera in their gold on their navy (DRAWN)
  let { look, logo = null }: { look: Look; logo?: string | null } = $props();
  const DRAWN: Look[] = ['cheer', 'moments', 'faces', 'aichekbtu', 'crystalkbtu', 'arthousekbtu', 'choice', 'kbtucinema'];
  // the official logos we ship: this file whatever the org's avatar is
  const OFFICIAL: Partial<Record<Look, string>> = { studex: studexLogo, moments: momentsLogo, knights: knightsLogo, shadekbtu: shadeLogo,
    teentertainmentkbtu: oteLogo, kbtumag: magLogo, cybersportkbtu: cyberLogo, diceanddestinykbtu: ddLogo,
    thebayharborsociety: bhLogo, qoloner: qolonerLogo,
    // the archive's Dota medallions, drawn with their scenes (the same files are the QR's mark)
    ...Object.fromEntries(Object.entries(ARCHIVE_LOOKS).map(([k, c]) => [k, c.mark])) };
  const own = $derived(logo && !DRAWN.includes(look) && !isSchool(look) ? logo : null);
</script>

<span class="medal {look}" class:club={!!clubLook(look)} aria-hidden="true">
  <span class="face">{#if look === 'sower'}<KbtuMark size={20} />{:else if look === 'aichekbtu'}<img src={aicheMedal} alt="" draggable="false" />{:else if OFFICIAL[look]}<img src={OFFICIAL[look]} alt="" draggable="false" />{:else if own}<img src={own} alt="" draggable="false" />{:else}<LookMark {look} />{/if}</span>
  <i class="catch"></i>
</span>

<style>
  /* a minted plate: a bevelled metal rim, the mark set into it, a soft drop onto the card */
  /* a finer rim (2 px) and the face's corner concentric with it */
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
  .knights { --rim: linear-gradient(145deg, rgb(255, 255, 255), rgb(120, 158, 228) 45%, rgb(236, 243, 255) 62%, rgb(28, 66, 150)); } /* their blue steel */
  .studex { --rim: linear-gradient(145deg, rgb(255, 255, 255), rgb(214, 38, 27) 45%, rgb(255, 210, 200) 62%, rgb(23, 48, 100)); }
  .moments { --rim: linear-gradient(145deg, rgb(246, 231, 214), rgb(196, 109, 71) 45%, rgb(242, 222, 200) 62%, rgb(110, 51, 34)); }
  .faces { --rim: linear-gradient(145deg, rgb(110, 123, 255), rgb(192, 75, 255) 40%, rgb(255, 79, 154) 70%, rgb(255, 164, 61)); }
  .club { --rim: linear-gradient(145deg, rgba(255, 255, 255, 0.95), var(--s2) 42%, var(--h1) 62%, var(--s1)); }
  /* the archive's Dota rims: old gold, jade into ember, ice into indigo */
  .dota_ancient { --rim: linear-gradient(145deg, rgb(255, 240, 200), rgb(199, 138, 44) 42%, rgb(246, 213, 140) 62%, rgb(110, 26, 14)); }
  .dota_clash { --rim: linear-gradient(145deg, rgb(223, 255, 240), rgb(47, 174, 134) 40%, rgb(255, 246, 230) 50%, rgb(224, 69, 28) 60%, rgb(90, 14, 10)); }
  .dota_rune { --rim: linear-gradient(145deg, rgb(244, 254, 255), rgb(122, 223, 255) 40%, rgb(232, 253, 255) 55%, rgb(90, 108, 255) 75%, rgb(30, 22, 102)); }
  /* SOWER (.claude/reports/sower-badge, card C): a plain white tile, the colonnade in black, no metal rim */
  .sower { padding: 0; border-radius: var(--r-s); background: rgb(245, 245, 247); box-shadow: 0 6px 14px rgba(0, 0, 0, 0.5); }
  .sower .face { display: grid; place-items: center; border-radius: inherit; background: none; color: rgb(11, 11, 12); }
  .sower .face::after { content: none; }
  .sower .catch { display: none; }
</style>
