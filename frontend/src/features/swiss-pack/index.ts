// NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OCE.
// Side-effect import: registers swiss_pack.* translations with i18next.
// Must run before Sidebar.tsx looks up `swiss_pack.nav` at boot.
import './i18n';
import './i18n-fr-ch-overrides';
import './i18n-fr-completion';

export { SwissPackPage } from './SwissPackPage';

