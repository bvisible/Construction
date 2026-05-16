/**
 * NEOFFICE FILE — Swiss Pack i18n bundle.
 * Owned 100% by Neoservice. Not from upstream OCE.
 * Created: 2026-05-01
 *
 * Side-effect import: registers swiss_pack.* translation keys with i18next
 * the moment this module is loaded. Re-exported from ./index.ts so any
 * caller importing { SwissPackPage } also picks up the translations.
 *
 * Locales kept minimal (EN + 3 Swiss official languages: FR/DE/IT).
 * Suisse romande is the primary market → French is the canonical default.
 */
import i18n from '@/app/i18n';

const swissPackTranslations: Record<string, Record<string, string>> = {
  en: {
    'swiss_pack.nav': 'Switzerland (CH)',
    'swiss_pack.title': 'Swiss Pack',
  },
  fr: {
    'swiss_pack.nav': 'Suisse (CH)',
    'swiss_pack.title': 'Pack Suisse',
  },
  de: {
    'swiss_pack.nav': 'Schweiz (CH)',
    'swiss_pack.title': 'Swiss Pack',
  },
  it: {
    'swiss_pack.nav': 'Svizzera (CH)',
    'swiss_pack.title': 'Pacchetto Svizzero',
  },
};

for (const [lng, keys] of Object.entries(swissPackTranslations)) {
  i18n.addResourceBundle(lng, 'translation', keys, true, true);
}

export { swissPackTranslations };
