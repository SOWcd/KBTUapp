<script lang="ts">
  // The organisation's medallion in the profile card's top right corner, where the QR was (owner, Nov 2: the QR lives on
  // the full-screen badge, MyQr): the club's logo, the school's shield, the KBTU mark, the creator's seal for SOWER,
  // set in a rim in the look's own metal (its colours, lib/awards.ts lookVars), a light catching it as the phone tilts.
  import { clubLook, type Look } from '../lib/awards';
  import LookMark from './LookMark.svelte';
  import Founder from './Founder.svelte';

  let { look }: { look: Look } = $props();
</script>

<span class="medal {look}" class:club={!!clubLook(look)} aria-hidden="true">
  <span class="face">{#if look === 'sower'}<Founder size={52} />{:else}<LookMark {look} />{/if}</span>
  <i class="catch"></i>
</span>

<style>
  /* a minted plate: a bevelled metal rim, the mark set into it, a soft drop onto the card */
  .medal { position: relative; display: block; width: 100%; height: 100%; padding: 3px; border-radius: var(--r-m);
    background: var(--rim, linear-gradient(145deg, rgb(255, 255, 255), rgb(176, 184, 202) 42%, rgb(244, 246, 251) 62%, rgb(140, 150, 172)));
    box-shadow: 0 12px 20px -10px rgba(0, 0, 0, 0.7), 0 2px 5px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.9), inset 0 -1px 1px rgba(0, 0, 0, 0.25); }
  .face { display: block; width: 100%; height: 100%; overflow: hidden; border-radius: var(--r-s); box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.45); }
  .face :global(.appmark) { border-radius: var(--r-s); box-shadow: none; }
  .face :global(.appmark img) { width: 80%; height: 80%; }
  /* the light: one band sliding with the tilt across the rim and the face (the strip's mechanism; still at rest) */
  .catch { position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    background: linear-gradient(115deg, transparent 38%, rgba(255, 255, 255, 0.3) 50%, transparent 62%) calc(12% + var(--gx, 0) * 130%) 0 / 260% 100% no-repeat,
      radial-gradient(120% 70% at 30% 0%, rgba(255, 255, 255, 0.22), transparent 60%); }
  /* each look's metal: Cheer's gold, Knights' blue steel, the clubs' and schools' own two strap colours with a light edge */
  .cheer { --rim: linear-gradient(145deg, rgb(255, 238, 190), rgb(196, 154, 64) 45%, rgb(236, 204, 128) 62%, rgb(150, 112, 40)); }
  .knights { --rim: linear-gradient(145deg, rgb(230, 240, 255), rgb(47, 107, 208) 45%, rgb(160, 196, 250) 62%, rgb(14, 42, 98)); }
  .studex { --rim: linear-gradient(145deg, rgb(255, 255, 255), rgb(214, 38, 27) 45%, rgb(255, 210, 200) 62%, rgb(23, 48, 100)); }
  .moments { --rim: linear-gradient(145deg, rgb(246, 231, 214), rgb(196, 109, 71) 45%, rgb(242, 222, 200) 62%, rgb(110, 51, 34)); }
  .faces { --rim: linear-gradient(145deg, rgb(110, 123, 255), rgb(192, 75, 255) 40%, rgb(255, 79, 154) 70%, rgb(255, 164, 61)); }
  .club { --rim: linear-gradient(145deg, rgba(255, 255, 255, 0.95), var(--s2) 42%, var(--h1) 62%, var(--s1)); }
  /* the creator's seal is round: its own rim */
  .sower { padding: 0; border-radius: 50%; background: none; box-shadow: 0 12px 20px -10px rgba(0, 0, 0, 0.8); }
  .sower .face { display: flex; align-items: center; justify-content: center; border-radius: 50%; box-shadow: none; }
  .sower .catch { border-radius: 50%; }
</style>
