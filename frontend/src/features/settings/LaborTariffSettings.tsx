/**
 * LaborTariffSettings — calibrate the composed labour tariff and the risk &
 * profit margins.
 *
 * Two scopes, one component:
 *   - no `projectId` → the COMPANY defaults every new project inherits
 *     (this is the "general variables" the estimator was looking for);
 *   - with `projectId` → that project's overrides. A field left empty simply
 *     inherits, and the inherited value is shown as the placeholder so it is
 *     always obvious which number will actually be used.
 *
 * Persisted via GET/PUT /neoffice/labor-tariff/params/ (?project_id=…), which
 * returns { effective, company, project, defaults }.
 */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Card, CardHeader, CardContent, Button } from '@/shared/ui';
import { apiGet, apiPut } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';

type ParamKey =
  | 'salaire_base_horaire'
  | 'charges_pct'
  | 'repas_jour'
  | 'indemnite_jour'
  | 'heures_jour'
  | 'charges_depot_h'
  | 'charges_bureau_h'
  | 'marge_mo_pct'
  | 'marge_materiaux_pct'
  | 'marge_machines_pct'
  | 'marge_outillage_pct'
  | 'marge_tiers_pct'
  | 'arrondi_chf';

type ParamMap = Partial<Record<ParamKey, string>>;

interface ParamsResponse {
  effective: Record<string, string>;
  company: ParamMap;
  project: ParamMap;
  defaults: Record<string, string>;
}

interface Field {
  key: ParamKey;
  label: string;
  hint: string;
}

/** The hourly cost build-up. */
const LABOUR_FIELDS: Field[] = [
  { key: 'salaire_base_horaire', label: 'Salaire moyen brut (CHF/h)', hint: 'Base du calcul — moyenne de l’équipe' },
  { key: 'charges_pct', label: 'Charges sociales (fraction)', hint: 'Ex. 0.42 = 42 % (charges employeur + 13e / vacances)' },
  { key: 'repas_jour', label: 'Repas / jour (CHF)', hint: 'Dîner + petit-déjeuner' },
  { key: 'indemnite_jour', label: 'Indemnité de chantier / jour (CHF)', hint: 'OFAS' },
  { key: 'heures_jour', label: 'Heures productives / jour', hint: '≈ 8.4' },
  { key: 'charges_depot_h', label: 'Charges dépôt (CHF/h)', hint: 'Charges du dépôt réparties sur l’heure productive' },
  { key: 'charges_bureau_h', label: 'Charges bureau (CHF/h)', hint: 'Charges administratives réparties sur l’heure productive' },
];

/** Risk & profit, per resource family — the "Risques et bénéfices" zone. */
const MARGIN_FIELDS: Field[] = [
  { key: 'marge_mo_pct', label: 'Main-d’œuvre', hint: 'Fraction — 0.12 = 12 %' },
  { key: 'marge_materiaux_pct', label: 'Matériaux', hint: 'Fraction — 0.10 = 10 %' },
  { key: 'marge_machines_pct', label: 'Machines', hint: 'Fraction' },
  { key: 'marge_outillage_pct', label: 'Outillage', hint: 'Fraction' },
  { key: 'marge_tiers_pct', label: 'Sous-traitants', hint: 'Fraction' },
  { key: 'arrondi_chf', label: 'Arrondi du prix (CHF)', hint: '0.50 = arrondi au demi-franc · 0 = pas d’arrondi' },
];

export function LaborTariffSettings({ projectId }: { projectId?: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const scopeQuery = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';

  const { data } = useQuery<ParamsResponse>({
    queryKey: ['neoffice', 'labor-params', projectId ?? 'company'],
    queryFn: () => apiGet<ParamsResponse>(`/v1/neoffice/labor-tariff/params/${scopeQuery}`),
  });

  // Only what THIS scope overrides is edited; empty means "inherit".
  const [form, setForm] = useState<ParamMap | null>(null);
  useEffect(() => {
    if (data) setForm(projectId ? { ...data.project } : { ...data.company });
  }, [data, projectId]);

  const save = useMutation({
    mutationFn: (p: ParamMap) => apiPut<ParamMap>(`/v1/neoffice/labor-tariff/params/${scopeQuery}`, p),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['neoffice'] });
      addToast({
        type: 'success',
        title: t('settings.labor_saved', { defaultValue: 'Paramètres enregistrés' }),
      });
    },
  });

  if (!form || !data) return null;

  /** Value used when this scope leaves the field empty. */
  const inherited = (key: ParamKey): string =>
    (projectId ? data.company[key] : undefined) ?? data.defaults[key] ?? '';

  const renderField = (f: Field) => {
    const value = form[f.key] ?? '';
    const isInheriting = value.trim() === '';
    return (
      <label key={f.key} className="flex flex-col gap-1">
        <span className="text-sm font-medium text-content-primary">
          {t(`settings.labor_${f.key}`, { defaultValue: f.label })}
        </span>
        <input
          type="text"
          inputMode="decimal"
          value={value}
          onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
          placeholder={inherited(f.key)}
          className="rounded-lg border border-border-light bg-surface-secondary px-3 py-2 text-sm tabular-nums focus:border-oe-blue focus:outline-none"
          autoComplete="new-password"
          name={`neoffice-${f.key}`}
        />
        <span className="text-2xs text-content-tertiary">
          {f.hint}
          {projectId && isInheriting && inherited(f.key) !== '' ? (
            <> · <span className="italic">hérité : {inherited(f.key)}</span></>
          ) : null}
        </span>
      </label>
    );
  };

  return (
    <Card className="lg:col-span-2">
      <CardHeader
        title={t('settings.labor_title', {
          defaultValue: projectId
            ? 'Main-d’œuvre & marges — ce projet'
            : 'Main-d’œuvre & marges — valeurs par défaut',
        })}
        subtitle={t('settings.labor_subtitle', {
          defaultValue: projectId
            ? 'Ces valeurs ne s’appliquent qu’à ce projet. Laissez un champ vide pour reprendre la valeur par défaut de l’entreprise (affichée en gris).'
            : 'Valeurs reprises par chaque nouveau projet. Un projet peut ensuite les ajuster sans toucher à celles-ci.',
        })}
      />
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{LABOUR_FIELDS.map(renderField)}</div>

        <div className="mt-6 border-t border-border-light pt-4">
          <h4 className="mb-1 text-sm font-semibold text-content-primary">
            {t('settings.margins_title', { defaultValue: 'Risques et bénéfices' })}
          </h4>
          <p className="mb-3 text-2xs text-content-tertiary">
            {t('settings.margins_subtitle', {
              defaultValue:
                'Marge appliquée au prix de vente, par famille de ressource. Le coût de revient reste affiché séparément.',
            })}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">{MARGIN_FIELDS.map(renderField)}</div>
        </div>

        <div className="mt-4 flex justify-end">
          <Button onClick={() => save.mutate(form)} disabled={save.isPending}>
            {t('common.save', { defaultValue: 'Enregistrer' })}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
