export { AppLayout } from './AppLayout';
export { Sidebar } from './Sidebar';
export { Header } from './Header';
// //// NEOFFICE PATCH — Export Frappe-embedded layout
// WHY: FrappeLayout / FrappeSidebar / FrappeNavbar are NEOFFICE FILE
// (entirely Neoservice). Re-export from this barrel so App.tsx can swap
// AppLayout → FrappeLayout via the EmbeddedLayout const at the top of App.tsx.
// REVIEW: permanent (couples to FrappeLayout swap in App.tsx).
export { FrappeLayout } from './FrappeLayout';
// //// END NEOFFICE PATCH
