// A club's or school's lanyard art as the background of its cards in the Clubs tab (tools/scene-rasters.mjs makes them).
import type { OrgRef } from './api';
import { skinOf } from './awards';

const ART = import.meta.glob('../assets/lanyards/covers/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
export const artOf = (o: OrgRef): string | undefined => ((s) => (s ? ART[`../assets/lanyards/covers/${s}.webp`] : undefined))(skinOf(o));
