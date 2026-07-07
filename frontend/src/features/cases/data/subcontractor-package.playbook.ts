// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Case: "Run a subcontractor package".
//
// Award a trade package to a subcontractor, put it on a contract and pay it
// down through progress claims with retention held. Content strings are key
// plus inline English default and live only here.

import type { Playbook } from '../types';

const playbook: Playbook = {
  id: 'subcontractor-package',
  order: 65,
  category: 'commercial',
  companyTypes: ['general-contractor', 'subcontractor', 'cost-consultant'],
  icon: 'PackageCheck',
  titleKey: 'cases.subcontractor_package.title',
  titleDefault: 'Run a subcontractor package',
  descKey: 'cases.subcontractor_package.desc',
  descDefault:
    'Award a trade package to a subcontractor, place it on a subcontract with a schedule of values and retention, then pay it down claim by claim against work actually done.',
  estMinutes: 11,
  steps: [
    {
      id: 'subbie',
      icon: 'Users',
      titleKey: 'cases.subcontractor_package.step.subbie.title',
      titleDefault: 'Set up the subcontractor',
      whatKey: 'cases.subcontractor_package.step.subbie.what',
      whatDefault:
        'Set up the subcontractor with their scope of works, and log the checks you require before they start: current insurance, trade qualifications, method statements and any prequalification score.',
      whyKey: 'cases.subcontractor_package.step.subbie.why',
      whyDefault:
        'A package is only as reliable as the firm you handed it to. The insurance certificate and qualification checks captured up front are what cover you if the work turns bad or a claim lands and the paperwork is challenged.',
      moduleLabel: 'Subcontractors',
      moduleLabelKey: 'onboarding.mod_subcontractors',
      to: '/projects/:projectId/subcontractors',
    },
    {
      id: 'contract',
      icon: 'FileSignature',
      titleKey: 'cases.subcontractor_package.step.contract.title',
      titleDefault: 'Put it on a contract',
      whatKey: 'cases.subcontractor_package.step.contract.what',
      whatDefault:
        'Draw up the subcontract with the agreed lump sum, the schedule of values that each claim will be measured against and the retention percentage you will hold on every payment.',
      whyKey: 'cases.subcontractor_package.step.contract.why',
      whyDefault:
        'A clear schedule of values is the ruler every future claim gets measured with, so there is no arguing over what a payment covers. The retention you withhold now is the leverage that gets snags fixed after the subcontractor has moved on.',
      moduleLabel: 'Contracts',
      moduleLabelKey: 'onboarding.mod_contracts',
      to: '/projects/:projectId/contracts',
    },
    {
      id: 'claim',
      icon: 'ReceiptText',
      titleKey: 'cases.subcontractor_package.step.claim.title',
      titleDefault: 'Pay down with progress claims',
      whatKey: 'cases.subcontractor_package.step.claim.what',
      whatDefault:
        'Each valuation period, certify the percentage complete against each schedule of values line, deduct retention and record what is actually paid. The subcontract carries the running balance forward automatically.',
      whyKey: 'cases.subcontractor_package.step.claim.why',
      whyDefault:
        'Certifying line by line against the schedule of values means you pay for work in the ground, not for a subcontractor optimistic view of it. The running balance flags an over-claim before you certify it, not after the money has gone.',
      moduleLabel: 'Contracts',
      moduleLabelKey: 'onboarding.mod_contracts',
      to: '/projects/:projectId/contracts',
    },
  ],
};

export default playbook;
