// The campus map's named places in Kazakh and English, kept out of kk.ts and en.ts: the map (lib/map.ts) knows a place
// by its name in any language from the start, while those dictionaries load after the first screen.
import type { Dict } from './ru';

type Spots = { [K in keyof Dict as K extends `route.spot.${string}` ? K : never]: string };

export const KK_SPOTS: Spots = {
  'route.spot.canteen': "Асхана",
  'route.spot.cowork': "Halyk Co-working",
  'route.spot.kunaev': "Қонаев аудиториясы",
  'route.spot.farabi': "Әл-Фараби холы",
  'route.spot.indep': "Тәуелсіздік залы",
  'route.spot.library': "Кітапхана",
  'route.spot.career': "Мансап орталығы",
  'route.spot.students': "Студенттермен жұмыс",
  'route.spot.site': "АТ және инженерия мектебі",
  'route.spot.energy': "Энергетика мектебі",
  'route.spot.marine': "Теңіз академиясы",
  'route.spot.gamedev': "Gamedev зертханасы",
  'route.spot.honeywell': "Honeywell зертханасы",
  'route.spot.security': "Қауіпсіздік қызметі",
  'route.spot.dispatch': "Диспетчерлік",
  'route.spot.rector': "Ректор",
  'route.spot.vrScience': "Ғылым жөніндегі проректор",
  'route.spot.vrSocial': "Әлеуметтік мәселелер проректоры",
  'route.spot.legal': "Заң департаменті",
  'route.spot.accounting': "Бухгалтерия",
};

export const EN_SPOTS: Spots = {
  'route.spot.canteen': "Canteen",
  'route.spot.cowork': "Halyk Co-working",
  'route.spot.kunaev': "Kunaev Hall",
  'route.spot.farabi': "Al-Farabi Hall",
  'route.spot.indep': "Independence Hall",
  'route.spot.library': "Library",
  'route.spot.career': "Career Center",
  'route.spot.students': "Student Affairs",
  'route.spot.site': "School of IT and Engineering",
  'route.spot.energy': "School of Energy",
  'route.spot.marine': "Maritime Academy",
  'route.spot.gamedev': "Gamedev Lab",
  'route.spot.honeywell': "Honeywell Lab",
  'route.spot.security': "Security Service",
  'route.spot.dispatch': "Dispatch Office",
  'route.spot.rector': "Rector",
  'route.spot.vrScience': "Vice-Rector for Science",
  'route.spot.vrSocial': "Vice-Rector for Social Affairs",
  'route.spot.legal': "Legal Department",
  'route.spot.accounting': "Accounting",
};
