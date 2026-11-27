// Spy's places: the server's ids (lib/i18n/spyPlaces.ts, the games' chunk only) and a place's name in my language.
import { i18n } from '../../lib/i18n/index.svelte';
import { PLACE_NAMES, PLACES, type Place } from '../../lib/i18n/spyPlaces';

export { PLACES, type Place };
export const placeName = (id: string): string => PLACE_NAMES[i18n.lang][id as Place] ?? id;
