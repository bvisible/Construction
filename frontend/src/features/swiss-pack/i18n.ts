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
    'onboarding.mod_swiss_pack': 'Regional Pack — Switzerland (CH)',
    'onboarding.mod_swiss_pack_desc': 'CFC, eBKP-H/T, NPK classifications + SIA norms (102/103/108/118), Swiss VAT (8.1%/2.6%/3.8%), SIA 118 contract types, CN labor classes, OFAS/SUVA/KBOB.',
  },
  fr: {
    'swiss_pack.nav': 'Suisse (CH)',
    'swiss_pack.title': 'Pack Suisse',
    'onboarding.mod_swiss_pack': 'Pack régional — Suisse (CH)',
    'onboarding.mod_swiss_pack_desc': 'Classifications CFC, eBKP-H/T, NPK + normes SIA (102/103/108/118), TVA Suisse (8.1%/2.6%/3.8%), contrats SIA 118, classes CN, OFAS/SUVA/KBOB.',
  },
  de: {
    'swiss_pack.nav': 'Schweiz (CH)',
    'swiss_pack.title': 'Swiss Pack',
    'onboarding.mod_swiss_pack': 'Regionalpaket — Schweiz (CH)',
    'onboarding.mod_swiss_pack_desc': 'Klassifikationen CFC, eBKP-H/T, NPK + SIA-Normen (102/103/108/118), Schweizer MwSt (8.1%/2.6%/3.8%), SIA-118-Vertragsarten, CN-Lohnklassen, AHV/SUVA/KBOB.',
  },
  it: {
    'swiss_pack.nav': 'Svizzera (CH)',
    'swiss_pack.title': 'Pacchetto Svizzero',
    'onboarding.mod_swiss_pack': 'Pacchetto regionale — Svizzera (CH)',
    'onboarding.mod_swiss_pack_desc': 'Classificazioni CFC, eBKP-H/T, NPK + norme SIA (102/103/108/118), IVA svizzera (8.1%/2.6%/3.8%), contratti SIA 118, classi CN, OFAS/SUVA/KBOB.',
  },
};

for (const [lng, keys] of Object.entries(swissPackTranslations)) {
  i18n.addResourceBundle(lng, 'translation', keys, true, true);
}

export { swissPackTranslations };
