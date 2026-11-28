# DESIGN.md: the owner's taste, the one source every designer reads

Every UI brief (Fable or any other designer) starts by reading this file, and every design critic judges against it.
The rules come from the owner's own words. When one of them is wrong, fix this file; do not work around it.

## The bar
Super modern, super beautiful and professional, at the level of the best iOS apps. One design code across the whole app: a new
screen must look like it was always part of it. Apple-level minimalism. Speed comes first (AGENTS.md goal 1).

## Anchors: what he likes (start from these, never from nothing)
- **Profile tab.** No page H1. It opens with one physical object (the lanyard badge). Everything else sits on rounded surface
  cards, each with its own head (title left, count right) on a 16 px rhythm, as grouped rows with hairlines.
- **Lanyard badges** (Profile, recruiting cards on Clubs). A club with a badge always shows its REAL badge art, never a
  generated background.
- **Afisha hero** (`web/src/screens/afisha/HeroArt.svelte`, #493 r4). Words sit on the cover itself, with no inner box.
- **The top-right context menu.** He likes its animation. It is the base for the app's motion language (see Motion).
- **The bottom tab bar is the gold standard of Liquid Glass**: he finds it gorgeous, juicy and beautiful. The rounded edges,
  the highlights and the rim light are the look every glass surface should reach.
- **Floating glass islands.** The tab bar and the title capsule float over content. Bottom actions are islands too, never full-width bars.
- **Pure black dark theme** (like iOS). Restrained Liquid Glass, monochrome. The pink/blue rim fringe is liked on glass
  capsules, but not on every chip and tile.
- **3D objects** in the app's own style (the orb, the lanyards), with iridescence kept inside the object.
- The pitch site `web/public/pitch.html` (he called it "gorgeous").

## The design code: Apple's Liquid Glass (iOS 26 HIG), adopted on purpose
- Controls and navigation are floating glass islands over the content: tab bar, title capsule, sheet actions, toolbars, menus.
  They never form full-width bars.
- Content is never glass. Cards, lists and text sit on solid surfaces beneath the islands. Glass on content turns muddy.
- One glass recipe for every island: the tab bar's.

## Never (he has rejected each of these, most of them more than once)
- Coloured rounded-square icon tiles (iOS Settings style): "always childish". Use monochrome line icons, a 3D object, or type.
- Muddy blur. A blurred copy of a poster under text turns bright posters into a brown or grey smear. Use a clean dark gradient
  scrim, or text where the picture is calm.
- Eye-searing saturated buttons (the bright blue "Going" button). The primary action is a calm white/ink capsule or glass.
- Bars pinned to the bottom that eat the screen, and actions that are always visible when they are rarely needed
  (Draft/Publish on the editor).
- A duplicated Back. Telegram's BackButton is the only Back (AGENTS.md).
- Tinting a whole screen in the event or club colour.
- Web-style giant H1 page titles, and loose section headings floating on the ground.
- Endless lists to scroll through. Show a short list (about 6) plus "All N", which opens the full list.
- Letterboxed or cropped avatars and logos (black bars): every avatar and logo fills its shape (object-fit: cover).
- Coloured status rings around avatars (the green "event coming up" ring): old-fashioned. Use no ring, or a subtle modern cue.
- Glow that leaks: only the active card glows, never the neighbours peeking in a carousel.
- Flat emoji boxes as a poster stand-in. Copying another product's layout (the Luma-style editor).
- Gambling or casino looks: chips, points, bets, card tables (a university rule).
- Rainbow gradient text, aurora backgrounds, glass on every card ("too childish").

## Motion
Based on the context menu's animation: spring, short, a few px, transform and opacity only, no animated blur or
clip-path, smooth on a mid-range Android. One motion language for sheets, menus, cards and tabs.
Criticism of an effect means improve it, never remove it.

## How design work is done here
1. Brief: the goal, the anchors above (with their screenshots), keep every function, and full freedom on layout.
   Never "from scratch" with no anchor (it comes out in another style), and never a vague "improve it".
   For a full redo, do not show the old screen, so it is not copied.
2. Build on tokens (`web/src/ui/tokens.css`). The design ratchet keeps new files at 0 raw values. A piece that ui/ lacks is
   added to ui/ in the same PR. A screen-local piece moves to ui/ once a second screen needs it.
3. Check on REAL content: real posters (the `real-posters` CI artifact), bright, dark and busy ones, long titles, 320 px, both
   themes. Drawn fixtures alone hide the worst cases.
4. Fable builds. An Opus critic reviews against this file. Fable fixes. The owner sees screenshots and picks. An adversarial
   pre-merge review runs. Merge, and the owner judges on prod. One screen per PR.
