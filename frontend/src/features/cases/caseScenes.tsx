// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Cases - bespoke line-art scenes for cases that have no generated picture yet.
//
// Each scene is a small concrete illustration of WHAT the case does, drawn in
// the exact same visual language as StepScene: the shared `0 0 120 84` viewBox,
// the faint blueprint grid, the shared colour palette (stepSceneParts `C`) and
// the same primitive kit (sheets, chips, cubes, badges, ...). That way a case
// without a webp illustration still reads like the detailed majority of the hub
// instead of a lone centred icon (the same idea as RoleArt falling back to a
// drawn avatar rather than a glyph).
//
// Keyed by case id. CaseArt renders the matching scene ahead of the picture, so
// only the cases listed here change; every other card is untouched.

import { type ReactElement } from 'react';
import clsx from 'clsx';
import {
  C,
  Badge,
  Bar,
  Chip,
  Cube,
  HeaderBand,
  RowBar,
  Sheet,
  Signature,
  Stamp,
  Star,
  WarnTri,
} from './stepSceneParts';
import { Grid, VB } from './StepScene';

/** A scene takes the one accent colour and returns its artwork group. */
type Scene = (accent: string) => ReactElement;

/**
 * Bespoke case illustrations, keyed by case id. Every scene uses the shared `C`
 * palette for fills and one `accent` highlight, exactly like the StepScene set,
 * so the linework reads identically on the always-light card tile.
 */
export const CASE_SCENES: Record<string, Scene> = {
  // 10 - Set up the common data environment: one shared store two people write
  // to and read from, kept under control (single source of truth).
  'set-up-the-common-data-environment': (accent) => (
    <>
      <Sheet x={38} y={16} w={44} h={52} />
      <HeaderBand x={38} y={16} w={44} h={10} fill={C.blue} />
      <RowBar x={45} y={20} w={18} h={3} fill={C.white} opacity={0.9} />
      <RowBar x={45} y={34} w={30} h={3.4} fill={C.grey3} />
      <RowBar x={45} y={43} w={26} h={3.4} fill={C.grey3} />
      <RowBar x={45} y={52} w={28} h={3.4} fill={C.grey3} />
      <circle cx={16} cy={30} r={6} fill={C.grey2} stroke="none" />
      <path d="M24 33 H37" stroke={accent} strokeWidth={2} fill="none" strokeLinecap="round" />
      <path
        d="M33 30 l4 3 l-4 3"
        stroke={accent}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={104} cy={54} r={6} fill={C.grey2} stroke="none" />
      <path d="M83 51 H96" stroke={C.blue} strokeWidth={2} fill="none" strokeLinecap="round" />
      <path
        d="M92 48 l4 3 l-4 3"
        stroke={C.blue}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Badge cx={78} cy={22} r={6} fill={C.green} glyph="check" />
    </>
  ),

  // 11 - Set up BIM requirements and coordination: a requirements checklist
  // that governs the model it is linked to.
  'set-up-bim-requirements-and-coordination': (accent) => (
    <>
      <Sheet x={20} y={14} w={44} h={56} />
      <HeaderBand x={20} y={14} w={44} h={10} fill={C.blue} />
      <RowBar x={27} y={18} w={20} h={3} fill={C.white} opacity={0.9} />
      <Badge cx={30} cy={34} r={4.5} fill={C.green} glyph="check" shadow={false} />
      <RowBar x={38} y={32} w={20} h={3.4} fill={C.grey3} />
      <Badge cx={30} cy={46} r={4.5} fill={C.green} glyph="check" shadow={false} />
      <RowBar x={38} y={44} w={16} h={3.4} fill={C.grey3} />
      <rect x={26} y={56} width={9} height={9} rx={2} fill={C.white} stroke={C.grey1} strokeWidth={1.6} />
      <RowBar x={38} y={59} w={18} h={3.4} fill={C.grey3} />
      <path d="M64 40 H76" stroke={C.grey1} strokeWidth={1.4} strokeDasharray="1 3" fill="none" />
      <Cube cx={88} ty={30} w={16} hh={8} depth={16} top={accent} />
    </>
  ),

  // 12 - Verify as-built against the model with a scan: a point cloud sweeps the
  // built model and the two are confirmed to match.
  'verify-as-built-against-the-model-with-a-scan': (accent) => (
    <>
      <Cube cx={54} ty={24} w={18} hh={9} depth={20} top={C.panel} left={C.grey3} right={C.grey2} />
      <circle cx={46} cy={34} r={1.5} fill={accent} stroke="none" />
      <circle cx={54} cy={40} r={1.5} fill={accent} stroke="none" />
      <circle cx={62} cy={36} r={1.5} fill={accent} stroke="none" />
      <circle cx={50} cy={48} r={1.5} fill={accent} stroke="none" />
      <circle cx={60} cy={50} r={1.5} fill={accent} stroke="none" />
      <circle cx={56} cy={30} r={1.5} fill={accent} stroke="none" />
      <rect x={12} y={62} width={11} height={8} rx={2} fill={C.ochre} stroke="none" />
      <path d="M23 64 L42 42" stroke={C.ochre} strokeWidth={1.6} strokeDasharray="2 3" fill="none" />
      <Badge cx={88} cy={26} r={8} fill={C.green} glyph="check" />
    </>
  ),

  // 22 - Draft an estimate with AI element matching: a bill whose rows get rates
  // suggested by an AI match, one highlighted.
  'draft-an-estimate-with-ai-element-matching': (accent) => (
    <>
      <Sheet x={22} y={14} w={54} h={56} />
      <HeaderBand x={22} y={14} w={54} h={10} fill={C.blue} />
      <RowBar x={28} y={18} w={16} h={3} fill={C.white} opacity={0.9} />
      <RowBar x={28} y={30} w={26} h={3.6} fill={C.grey3} />
      <Chip x={58} y={28} w={12} h={6} r={1.5} fill={C.grey2} />
      <RowBar x={28} y={40} w={22} h={3.6} fill={C.grey3} />
      <Chip x={58} y={38} w={12} h={6} r={1.5} fill={C.ochre} />
      <RowBar x={28} y={50} w={24} h={3.6} fill={C.grey3} />
      <Chip x={58} y={48} w={12} h={6} r={1.5} fill={C.grey2} />
      <Chip x={80} y={40} w={20} h={11} fill={C.blueLight} label="AI" />
      <path
        d="M80 45 C74 45 74 41 70 41"
        stroke={C.blue}
        strokeWidth={1.6}
        strokeDasharray="1 3"
        fill="none"
      />
      <Star cx={92} cy={22} r={6.5} fill={C.ochre} />
      <Star cx={103} cy={34} r={4} fill={C.blueLight} />
      <Star cx={84} cy={30} r={3.5} fill={accent} />
    </>
  ),

  // 23 - Build the resource library and rates: a catalogue of labour, plant and
  // material, each carrying its rate.
  'build-the-resource-library-and-rates': (accent) => (
    <>
      <Sheet x={24} y={12} w={72} h={60} />
      <HeaderBand x={24} y={12} w={72} h={11} fill={C.blue} />
      <RowBar x={30} y={16} w={24} h={3.4} fill={C.white} opacity={0.9} />
      <circle cx={34} cy={33} r={4} fill={C.grey2} stroke="none" />
      <path d="M30 40 c0 -4 2 -6 4 -6 s4 2 4 6 z" fill={C.grey2} stroke="none" />
      <RowBar x={44} y={33} w={24} h={3.4} fill={C.grey3} />
      <Chip x={76} y={31} w={14} h={7} fill={C.green} />
      <rect x={30} y={46} width={9} height={6} rx={1.5} fill={C.ochre} stroke="none" />
      <circle cx={32} cy={53} r={1.8} fill={C.blueDeep} stroke="none" />
      <circle cx={37} cy={53} r={1.8} fill={C.blueDeep} stroke="none" />
      <RowBar x={44} y={47} w={20} h={3.4} fill={C.grey3} />
      <Chip x={76} y={45} w={14} h={7} fill={accent} />
      <rect x={30} y={60} width={8} height={8} rx={1} fill={C.blueLight} stroke="none" />
      <RowBar x={44} y={62} w={22} h={3.4} fill={C.grey3} />
      <Chip x={76} y={60} w={14} h={7} fill={C.grey2} />
    </>
  ),

  // 24 - Build a 5D cost-loaded model: the 3D model carries a cost tag and rolls
  // up into a cost-over-time curve.
  'build-a-5d-cost-loaded-model': (accent) => (
    <>
      <Cube cx={40} ty={22} w={18} hh={9} depth={20} top={C.blueLight} left={C.blue} right={C.blueDeep} />
      <path d="M58 34 H70" stroke={C.grey1} strokeWidth={1.4} strokeDasharray="1 3" fill="none" />
      <Chip x={70} y={28} w={22} h={11} fill={C.green} />
      <circle cx={81} cy={33.5} r={3.2} fill="none" stroke={C.white} strokeWidth={1.4} />
      <path d="M24 68 H104" stroke={C.grey1} strokeWidth={1.2} fill="none" />
      <path
        d="M28 66 L48 60 L66 62 L86 50 L100 46"
        fill="none"
        stroke={C.blue}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={100} cy={46} r={2.6} fill={accent} stroke="none" />
    </>
  ),

  // 25 - Appraise a development scheme: does the scheme stack up, a building
  // weighed against the return it makes.
  'appraise-a-development-scheme': (accent) => (
    <>
      <rect x={26} y={24} width={26} height={44} rx={2} fill={C.blue} stroke="none" />
      <path
        d="M31 32 h4 M42 32 h4 M31 40 h4 M42 40 h4 M31 48 h4 M42 48 h4 M31 56 h4 M42 56 h4"
        stroke={C.blueLight}
        strokeWidth={3}
        strokeLinecap="round"
        fill="none"
      />
      <circle cx={70} cy={30} r={9} fill={C.ochre} stroke={C.white} strokeWidth={1.2} />
      <circle cx={70} cy={30} r={5.5} fill="none" stroke={C.white} strokeWidth={1.3} opacity={0.7} />
      <path
        d="M60 62 L72 54 L82 58 L96 42"
        fill="none"
        stroke={C.green}
        strokeWidth={2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M90 42 h6 v6"
        fill="none"
        stroke={accent}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M24 68 H100" stroke={C.grey1} strokeWidth={1.6} strokeLinecap="round" fill="none" />
    </>
  ),

  // 71 - Run the submittals register: a stack of submittals tracked through their
  // review statuses and stamped off.
  'run-the-submittals-register': (accent) => (
    <>
      <rect x={30} y={16} width={44} height={52} rx={4} fill={C.white} stroke={C.grey1} strokeWidth={1.4} />
      <rect x={36} y={20} width={44} height={52} rx={4} fill={C.white} stroke={C.grey1} strokeWidth={1.4} />
      <Sheet x={42} y={24} w={44} h={52} />
      <HeaderBand x={42} y={24} w={44} h={9} fill={C.blue} />
      <circle cx={49} cy={42} r={2.4} fill={C.green} stroke="none" />
      <RowBar x={54} y={40.5} w={24} h={3.2} fill={C.grey3} />
      <circle cx={49} cy={52} r={2.4} fill={C.amber} stroke="none" />
      <RowBar x={54} y={50.5} w={20} h={3.2} fill={C.grey3} />
      <circle cx={49} cy={62} r={2.4} fill={accent} stroke="none" />
      <RowBar x={54} y={60.5} w={22} h={3.2} fill={C.grey3} />
      <Stamp cx={80} cy={62} r={7} />
    </>
  ),

  // 72 - Turn field time into payroll and labour cost: a timesheet with hours
  // becomes paid labour cost.
  'turn-field-time-into-payroll-and-labour-cost': (accent) => (
    <>
      <Sheet x={18} y={18} w={38} h={48} />
      <HeaderBand x={18} y={18} w={38} h={9} fill={C.blue} />
      <RowBar x={24} y={34} w={26} h={3.2} fill={C.grey3} />
      <RowBar x={24} y={42} w={22} h={3.2} fill={C.grey3} />
      <RowBar x={24} y={50} w={24} h={3.2} fill={C.grey3} />
      <circle cx={49} cy={23} r={6.5} fill={C.white} stroke={C.blue} strokeWidth={1.8} />
      <path d="M49 19 v4 l3 2" stroke={C.blue} strokeWidth={1.6} fill="none" strokeLinecap="round" />
      <path
        d="M60 44 H74 M70 40 l4 4 l-4 4"
        stroke={accent}
        strokeWidth={2.2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect x={78} y={34} width={30} height={20} rx={3} fill={C.green} stroke="none" />
      <circle cx={93} cy={44} r={5} fill="none" stroke={C.white} strokeWidth={1.4} opacity={0.85} />
    </>
  ),

  // 73 - Build a delay and disruption claim with evidence: a slipped programme
  // bar, backed by an evidence record.
  'build-a-delay-and-disruption-claim-with-evidence': (accent) => (
    <>
      <Sheet x={14} y={14} w={64} h={40} />
      <path d="M22 26 h30" stroke={C.blue} strokeWidth={5} strokeLinecap="round" fill="none" />
      <path d="M22 36 h18" stroke={C.grey2} strokeWidth={5} strokeLinecap="round" fill="none" />
      <path d="M40 36 h20" stroke={C.red} strokeWidth={5} strokeLinecap="round" fill="none" />
      <path d="M22 46 h14" stroke={C.grey2} strokeWidth={5} strokeLinecap="round" fill="none" />
      <path d="M52 20 V50" stroke={accent} strokeWidth={1.6} strokeDasharray="2 2" fill="none" />
      <Sheet x={78} y={48} w={24} h={24} />
      <RowBar x={83} y={55} w={13} h={2.8} fill={C.grey3} />
      <RowBar x={83} y={61} w={10} h={2.8} fill={C.grey3} />
      <WarnTri cx={28} cy={64} w={16} fill={C.amber} />
    </>
  ),

  // 74 - Mark up and compare a drawing revision: a red mark-up on one revision,
  // resolved on the next, compared side by side.
  'mark-up-and-compare-a-drawing-revision': (accent) => (
    <>
      <Sheet x={14} y={16} w={38} h={52} fill={C.panel} />
      <path d="M20 30 H46 M20 44 H40 M28 24 V60" stroke={C.grey1} strokeWidth={1.2} fill="none" />
      <circle cx={34} cy={39} r={7} fill="none" stroke={C.red} strokeWidth={1.8} />
      <path d="M30 54 h12" stroke={C.red} strokeWidth={1.8} strokeLinecap="round" fill="none" />
      <Sheet x={68} y={16} w={38} h={52} fill={C.panel} />
      <path d="M74 30 H100 M74 44 H94 M82 24 V60" stroke={C.grey1} strokeWidth={1.2} fill="none" />
      <circle cx={88} cy={39} r={7} fill="none" stroke={C.green} strokeWidth={1.8} />
      <path
        d="M53 34 H66 M62 30 l4 4 l-4 4"
        stroke={C.blue}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M67 50 H54 M58 46 l-4 4 l4 4"
        stroke={accent}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </>
  ),

  // 75 - Give the client a project portal: the client sees the project's numbers
  // on their own screen.
  'give-the-client-a-project-portal': (accent) => (
    <>
      <rect x={22} y={16} width={62} height={44} rx={4} fill={C.white} stroke={C.grey1} strokeWidth={1.8} />
      <HeaderBand x={22} y={16} w={62} h={10} fill={C.blue} />
      <RowBar x={28} y={32} w={22} h={3.4} fill={C.grey3} />
      <RowBar x={28} y={40} w={18} h={3.4} fill={C.grey3} />
      <Bar x={56} baseY={52} w={5} h={10} fill={C.blueLight} />
      <Bar x={64} baseY={52} w={5} h={16} fill={C.blue} />
      <Bar x={72} baseY={52} w={5} h={8} fill={C.ochre} />
      <path d="M46 60 h16 l3 8 h-22 z" fill={C.grey2} stroke="none" />
      <path d="M36 68 H72" stroke={C.grey1} strokeWidth={2} strokeLinecap="round" fill="none" />
      <circle cx={96} cy={40} r={7} fill={accent} stroke={C.white} strokeWidth={1} />
      <path d="M86 62 c0 -8 4 -13 10 -13 s10 5 10 13 z" fill={accent} stroke={C.white} strokeWidth={1} />
    </>
  ),

  // 76 - Manage an engineering change: a part is revised under a controlled
  // change and approved.
  'manage-an-engineering-change': (accent) => (
    <>
      <circle cx={40} cy={42} r={14} fill={C.blue} stroke="none" />
      <path
        d="M40 22 V32 M40 52 V62 M20 42 H30 M50 42 H60 M30 32 l-6 -6 M50 32 l6 -6 M30 52 l-6 6 M50 52 l6 6"
        stroke={C.blue}
        strokeWidth={3.6}
        strokeLinecap="round"
        fill="none"
      />
      <circle cx={40} cy={42} r={6} fill={C.white} stroke="none" />
      <Chip x={64} y={16} w={16} h={8} fill={C.ochre} label="B" />
      <path
        d="M66 36 a12 12 0 0 1 24 3"
        fill="none"
        stroke={accent}
        strokeWidth={2.2}
        strokeLinecap="round"
      />
      <path
        d="M90 32 l0 8 l-8 -1"
        fill="none"
        stroke={accent}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Badge cx={86} cy={58} r={9} fill={C.green} glyph="check" />
    </>
  ),

  // 77 - Record a verbal instruction for the record: something said on site is
  // captured in a written, signed note.
  'record-a-verbal-instruction-for-the-record': (accent) => (
    <>
      <path
        d="M16 16 h40 a5 5 0 0 1 5 5 v16 a5 5 0 0 1 -5 5 H34 l-10 8 v-8 h-8 a5 5 0 0 1 -5 -5 V21 a5 5 0 0 1 5 -5 z"
        fill={C.blueLight}
        stroke="none"
      />
      <RowBar x={22} y={24} w={28} h={3.2} fill={C.white} opacity={0.85} />
      <RowBar x={22} y={31} w={20} h={3.2} fill={C.white} opacity={0.65} />
      <path
        d="M50 52 C58 56 62 56 70 54"
        stroke={accent}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M66 50 l5 4 l-6 3"
        stroke={accent}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Sheet x={72} y={40} w={34} h={34} />
      <RowBar x={78} y={48} w={20} h={3} fill={C.grey3} />
      <RowBar x={78} y={55} w={16} h={3} fill={C.grey3} />
      <Signature x={78} y={64} w={20} color={C.blue} />
    </>
  ),

  // 78 - Handover and closeout: the finished building is handed over, with the
  // keys passed and the works signed off.
  'handover-and-closeout': (accent) => (
    <>
      <rect x={22} y={30} width={30} height={38} rx={2} fill={C.blue} stroke="none" />
      <path d="M20 30 L37 20 L54 30 Z" fill={C.blueDeep} stroke="none" />
      <rect x={28} y={38} width={7} height={7} rx={1} fill={C.blueLight} stroke="none" />
      <rect x={39} y={38} width={7} height={7} rx={1} fill={C.blueLight} stroke="none" />
      <rect x={33} y={54} width={8} height={14} rx={1} fill={C.white} stroke="none" />
      <circle cx={68} cy={40} r={6} fill="none" stroke={C.ochre} strokeWidth={3} />
      <path
        d="M73 43 l12 12 M80 50 l4 -4 M84 54 l4 -4"
        stroke={C.ochre}
        strokeWidth={3}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Badge cx={92} cy={26} r={9} fill={C.green} glyph="check" />
      <Star cx={37} cy={16} r={4} fill={accent} />
      <path d="M20 68 H98" stroke={C.grey1} strokeWidth={1.6} strokeLinecap="round" fill="none" />
    </>
  ),
};

interface CaseSceneProps {
  /** Case id; selects the bespoke scene from {@link CASE_SCENES}. */
  id: string;
  /** Accent colour (hex) for the one highlight per scene. Defaults to oe-blue. */
  accent?: string;
  /** Extra classes for the svg (sizing). */
  className?: string;
  /** Accessible label; the scene is decorative when omitted. */
  title?: string;
}

/**
 * Renders the bespoke line-art scene for a case in the exact StepScene frame
 * (same viewBox, blueprint grid and slate linework), sized to fill its tile.
 * Returns `null` when the case has no bespoke scene, so callers can fall back.
 */
export function CaseScene({
  id,
  accent = '#2563eb',
  className,
  title,
}: CaseSceneProps): ReactElement | null {
  const scene = CASE_SCENES[id];
  if (!scene) return null;
  return (
    <svg
      viewBox={VB}
      className={clsx('h-full w-full p-3 text-slate-400', className)}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? 'img' : undefined}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : true}
    >
      <Grid />
      {scene(accent)}
    </svg>
  );
}
