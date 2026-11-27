// Spy's places, the server's ids (server/kbtu/logic/spy.py LOCATIONS, the same order: places.test.ts checks); each
// one's name is t(`spy.loc.<id>`) in ru/kk/en. The spy names one of these to win.
import type { Key } from '../../lib/i18n/ru';

export const PLACES = [
  'kbtu_canteen', 'kbtu_library', 'kbtu_dorm', 'kbtu_lecture', 'kbtu_gym', 'kbtu_deans', 'kbtu_lab', 'kbtu_atrium',
  'kbtu_graduation', 'kbtu_exam', 'kbtu_hackathon', 'kbtu_club_fair',
  'medeu', 'shymbulak', 'kok_tobe', 'green_bazaar', 'metro', 'mountain_lake', 'toi',
  'airport', 'train', 'hospital', 'bank', 'cinema', 'theatre', 'beach', 'restaurant', 'supermarket', 'hotel',
  'police', 'school', 'museum', 'zoo', 'space_station', 'submarine', 'circus', 'concert', 'pirate_ship',
  'film_set', 'barbershop', 'gas_station', 'coffee_shop', 'embassy', 'polar_station',
] as const;

export type Place = (typeof PLACES)[number];
export const placeKey = (id: string): Key => `spy.loc.${id}` as Key;
