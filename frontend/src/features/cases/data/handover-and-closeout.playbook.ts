// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Hand over and close out".
//
// Finish the job cleanly: clear the punch list, confirm inspections and open
// NCRs are closed, assemble the documents and issue the handover. Content
// strings are key plus inline English default and live only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'handover-and-closeout',
  order: 70,
  category: 'handover',
  companyTypes: ['general-contractor', 'project-manager', 'owner-operator'],
  icon: 'ShieldCheck',
  titleKey: 'cases.handover_and_closeout.title',
  titleDefault: 'Hand over and close out',
  descKey: 'cases.handover_and_closeout.desc',
  descDefault:
    'Finish the job cleanly: work the punch list to zero, confirm every inspection passed and no non-conformance is open, gather the as-built record and issue a signed handover.',
  estMinutes: 12,
  steps: [
    {
      id: 'punch',
      icon: 'ListChecks',
      titleKey: 'cases.handover_and_closeout.step.punch.title',
      titleDefault: 'Clear the punch list',
      whatKey: 'cases.handover_and_closeout.step.punch.what',
      whatDefault:
        'Walk the finished works room by room, log every snag with its location and a photo, assign each one to the trade responsible and track the list down to nothing.',
      whyKey: 'cases.handover_and_closeout.step.punch.why',
      whyDefault:
        'The punch list is the distance between practically complete and genuinely complete, and the client feels every open item. A short list driven to zero is usually what releases the final certificate and the last payment.',
      moduleLabel: 'Punch list',
      moduleLabelKey: 'nav.punchlist',
      to: '/punchlist',
    },
    {
      id: 'quality',
      icon: 'ClipboardCheck',
      titleKey: 'cases.handover_and_closeout.step.quality.title',
      titleDefault: 'Confirm quality is closed',
      whatKey: 'cases.handover_and_closeout.step.quality.what',
      whatDefault:
        'Confirm every required inspection is passed and no non-conformance is still open on the register. Each hold and witness point should carry its sign-off before you call quality complete.',
      whyKey: 'cases.handover_and_closeout.step.quality.why',
      whyDefault:
        'An NCR left open at handover becomes a liability that follows you into the occupied building and the defects period. Confirming every one is closed is what makes the handover pack both complete and honest.',
      moduleLabel: 'Inspections',
      moduleLabelKey: 'inspections.title',
      to: '/projects/:projectId/inspections',
    },
    {
      id: 'documents',
      icon: 'FolderOpen',
      titleKey: 'cases.handover_and_closeout.step.documents.title',
      titleDefault: 'Assemble the documents',
      whatKey: 'cases.handover_and_closeout.step.documents.what',
      whatDefault:
        'Collect the as-built drawings, test certificates, product warranties and operating manuals into the project files, indexed so the operator can find any one of them in one place.',
      whyKey: 'cases.handover_and_closeout.step.documents.why',
      whyDefault:
        'The client forgets a smooth pour but remembers a messy handover for years. A complete, well ordered document set is both the last impression you leave and the first thing the facilities team actually opens.',
      moduleLabel: 'Files',
      moduleLabelKey: 'nav.documents',
      to: '/projects/:projectId/files',
    },
    {
      id: 'closeout',
      icon: 'ShieldCheck',
      titleKey: 'cases.handover_and_closeout.step.closeout.title',
      titleDefault: 'Issue the handover',
      whatKey: 'cases.handover_and_closeout.step.closeout.what',
      whatDefault:
        'Pull the close-out package together, check that every gate from snags to certificates is met and issue the signed handover to both the client and the operator who takes the building on.',
      whyKey: 'cases.handover_and_closeout.step.closeout.why',
      whyDefault:
        'Close-out is what turns a finished building into a discharged contractual obligation rather than an open one. Issuing it cleanly sets the defects liability period running from an agreed, documented starting point.',
      moduleLabel: 'Close-out',
      moduleLabelKey: 'nav.closeout',
      to: '/closeout',
    },
  ],
};

export default playbook;
