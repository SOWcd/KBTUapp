// Spy's places, in the server's order (server/kbtu/logic/spy.py LOCATIONS; a server test holds the two equal):
// campus first, then the city's and the classic ones. Names: spy.loc.<id> in lib/i18n.
export const SPY_LOCATIONS = [
  'library', 'canteen', 'lecture_hall', 'dorm', 'gym', 'dean_office', 'lab', 'coworking', 'exam', 'graduation',
  'hackathon', 'assembly_hall', 'club_fair', 'career_fair', 'metro', 'bus', 'coffee_shop', 'hospital', 'airport',
  'train', 'cinema', 'museum', 'bank', 'restaurant', 'theater', 'space_station', 'submarine', 'zoo',
  'supermarket', 'shymbulak', 'green_bazaar', 'wedding', 'concert', 'beach', 'police_station', 'pirate_ship',
] as const;
export type SpyLocation = (typeof SPY_LOCATIONS)[number];
/** the room's link: its QR and "share to chat" open the app straight into the room */
export const roomLink = (code: string): string => `https://t.me/KBTUappBot?startapp=g_${code}`;
