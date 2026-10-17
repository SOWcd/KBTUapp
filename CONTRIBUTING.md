# Contributing

Thanks for wanting to make KBTU App better.

- **An idea or a bug:** open an issue, or write to [@Sowers](https://t.me/Sowers).
- **Code:** fork, make a branch, open a pull request against `main`. Keep it small and about one thing; say what it
  changes for students and how you checked it. The tests (`server/tests`, `web` vitest) and `npm run check` must pass.
- **Style:** match the code around your change. Code, comments and commit messages are in English; UI text lives
  only in `web/src/lib/i18n/` (ru, kk, en: add all three) and the bot's in `server/kbtu/texts.py`.
- **Data:** never commit real people's data, tokens or screenshots with personal details.
- **Database:** never edit `schema.sql`; append a migration to `MIGRATIONS` in `server/kbtu/db.py`.

Every pull request is reviewed by hand before it is merged; merged code goes live at kbtu.sow.kz.

## Your rights in what you send

KBTU App is licensed under the Business Source License 1.1 and its author licenses it to universities. So that
this stays possible, by submitting a contribution (code, text, images, anything in a pull request) you agree that:

1. it is your own work, or you have the right to submit it, and it contains nothing under terms incompatible
   with this;
2. you grant Nurmatov Sukhrab Rustamzhanovich (the Licensor) a perpetual, worldwide, non-exclusive, free,
   irrevocable license to use, copy, modify, distribute and sublicense it under any terms, including the
   project's current and future licenses and commercial licenses;
3. you will be credited in the project's history, and you receive no payment for it.

If you don't agree, please don't send a pull request; an issue with the idea is just as welcome.
