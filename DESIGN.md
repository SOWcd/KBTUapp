# DESIGN.md: the owner's taste, the one source every designer reads

Every UI brief (Fable or any other designer) starts by reading this file, and every design critic judges against it.
Sources: text in quotes and every **(owner)** rule are the owner's own verdicts (hard taste rules: change them only on his
word). Everything else is our generalization of them: when one blocks a task or accessibility, fix this file; do not work
around it.

## The bar
Super modern, super beautiful and professional, at the level of the best iOS apps. One design code across the whole app: a new
screen must look like it was always part of it. Apple-level minimalism. Speed comes first (AGENTS.md goal 1).

## Anchors: what he likes (start from these, never from nothing)
- **Profile tab.** No big visible page title (keep a semantic heading for screen readers). It opens with one physical object (the lanyard badge). Everything else sits on rounded surface
  cards, each with its own head (title left, count right) on a 16 px rhythm, as grouped rows with hairlines.
- **Lanyard badges** (Profile, and the recruiting cards on top of Clubs, which he likes: a club's own badge shown while it recruits). A club with a badge always shows its REAL badge art, never a
  generated background.
- **Afisha hero** (`web/src/screens/afisha/HeroArt.svelte`, #493 r4). Words sit on the cover itself, with no inner box.
- **The top-right context menu.** He likes its animation. It is the base for the app's motion language (see Motion).
- **The bottom tab bar is the gold standard of Liquid Glass**: he finds it gorgeous, juicy and beautiful. The rounded edges,
  the highlights and the rim light are the look every glass surface should reach.
- **Floating glass islands.** The tab bar and the title capsule float over content. Bottom actions are islands too, by preference.
- **Pure black dark theme** (like iOS). Restrained Liquid Glass, monochrome. The pink/blue rim fringe is liked on glass
  capsules, but not on every chip and tile.
- **3D objects** in the app's own style (the orb, the lanyards), with iridescence kept inside the object.
- The pitch site `web/public/pitch.html` (he called it "gorgeous").

## The design code: Apple's Liquid Glass (iOS 26 HIG), adopted on purpose
- Controls and navigation are floating glass islands over the content: tab bar, title capsule, sheet actions, toolbars, menus.
  Prefer islands to full-width bars; go wider only when task clarity or accessibility needs it (a long translated label,
  enlarged text). Essential actions stay reachable and never hide content.
- Content is never glass. Cards, lists and text sit on solid surfaces beneath the islands. Glass on content turns muddy.
- One material family with the tab bar's look as its benchmark, varied by size and background (a menu is more opaque
  than a small capsule: `--menu-bg` in `tokens.css`). Every button keeps the family's look (`ui/Button.svelte`); only
  floating controls blur what is under them.
- Apple's own before/after (the owner's reference): a full-width toolbar with coloured icons becomes small glass CAPSULES
  (related actions grouped) and round glass BUTTONS (a single action) floating over the content, with monochrome icons.
  Our pinned bars and decorative coloured icons are the "before". Toolbar icons default to monochrome; semantic colour
  (selection, status, a destructive red) stays, always backed by a label or shape. Semantic colour is a tint on a mark or label, never a
  saturated button fill or a coloured icon tile.

## Never (the **(owner)** items are his own verdicts, most given more than once)
- **(owner)** Coloured rounded-square icon tiles (iOS Settings style): "always childish". Use monochrome line icons, a 3D object, or type.
- **(owner)** Muddy blur. A blurred copy of a poster under text turns bright posters into a brown or grey smear. Use a clean dark gradient
  scrim, or text where the picture is calm.
- **(owner)** Eye-searing saturated buttons (the bright blue "Going" button). The primary action is a calm white/ink capsule or glass.
- Bars pinned to the bottom that eat the screen, and actions that are always visible when they are rarely needed
  (Draft/Publish on the editor).
- A duplicated Back. Telegram's BackButton is the only Back (AGENTS.md).
- Tinting a whole screen in the event or club colour.
- Web-style giant visible page titles, and loose section headings floating on the ground (semantic headings stay).
- Endless lists in summary sections: a preview shows about 6 plus "All N". Where browsing is the screen's main task
  (search, a feed, a full list) show it all and keep the scroll position.
- Black letterbox bars on avatars and logos. Photos fill their shape (cover, cropped around the face); logos and wordmarks
  stay whole (contain, with padding on a neutral surface; `ui/OrgLogo.svelte` still uses cover: a "before").
- Coloured status rings around avatars (the green "event coming up" ring): old-fashioned. Use no ring, or a subtle modern cue.
- **(owner)** Glow that leaks: only the active card glows, never the neighbours peeking in a carousel.
- Flat emoji boxes as a poster stand-in. Copying another product's layout (the Luma-style editor).
- **(owner)** Gambling or casino looks: chips, points, bets, card tables (a university rule).
- Rainbow gradient text, aurora backgrounds, glass on every card ("too childish").

## Motion
Based on the context menu's animation (`web/src/ui/Menu.svelte`): it grows out of its anchor with a springy overshoot
(about 400 ms in, 150 ms out), transform and opacity only, no animated blur or clip-path, smooth on a mid-range Android.
One motion language for sheets, menus, cards and tabs, each motion with a role. Criticism of an effect means improve it
first; simplify or remove it when it costs speed (goal 1 wins), hurts comprehension or comfort. Reduced motion is always
respected (`calm()` in `web/src/ui/fold.ts`: no spring, a plain fade or none) and motion never delays a tap.

## How design work is done here
1. Brief: the goal, the anchors above (with their screenshots), keep every function, and full freedom on layout.
   Never "from scratch" with no anchor (it comes out in another style), and never a vague "improve it".
   For a full redo, do not show the old screen, so it is not copied.
2. Build on tokens (`web/src/ui/tokens.css`). The design ratchet (`web/src/lib/design.test.ts`) keeps new `.svelte`
   files at 0 raw font sizes, radii, hex colours and off-scale weights. A piece that ui/ lacks is
   added to ui/ in the same PR. A screen-local piece moves to ui/ once a second screen needs it.
3. Check on REAL content: real posters (public event art: bright, dark and busy ones), long titles, 320 px, both themes.
   Drawn fixtures alone hide the worst cases. Also: enlarged text, reduced motion and transparency, screen-reader labels,
   keyboard focus, tap targets at least 44x44 CSS px, text contrast WCAG AA in both themes. Never real people's names,
   photos or handles in screenshots: use the made-up people `server/tools/qa.py` seeds.
4. Fable builds. An Opus critic reviews against this file. Fable fixes. The owner sees screenshots and picks. An adversarial
   pre-merge review runs. Merge, and the owner judges on prod. One screen per PR.
