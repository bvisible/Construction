/**
 * LaborTariffSettings — calibrate the composed labour tariff parameters.
 *
 * Protti's real hourly cost = base wage + these parameters + travel. Here the
 * estimator sets their own charges %, meal allowance, site allowance and
 * productive hours so the composed tariff (and the project SiteTravelCard) match
 * their actual rate. Persisted via GET/PUT /neoffice/labor-tariff/params/.
 */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Card, CardHeader, CardContent, Button } from '@/shared/ui';
import { apiGet, apiPut } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';

interface LaborParams {
  charges_pct: string;
  repas_jour: string;
  indemnite_jour: string;
  heures_jour: string;
}

const FIELDS: { key: keyof LaborParams; label: string; hint: string }[] = [
  { key: 'charges_pct', label: 'Charges sociales (fraction)', hint: 'Ex. 0.42 = 42 % (charges employeur + suppléments 13e / vacances)' },
  { key: 'repas_jour', label: 'Repas / jour (CHF)', hint: 'Dîner + petit-déjeuner' },
  { key: 'indemnite_jour', label: 'Indemnité de chantier / jour (CHF)', hint: 'OFAS' },
  { key: 'heures_jour', label: 'Heures productives / jour', hint: '≈ 8.4' },
];

export function LaborTariffSettings() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const { data } = useQuery<LaborParams>({
    queryKey: ['neoffice', 'labor-params'],
    queryFn: () => apiGet<LaborParams>('/v1/neoffice/labor-tariff/params/'),
  });
  const [form, setForm] = useState<LaborParams | null>(null);
  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const save = useMutation({
    mutationFn: (p: LaborParams) => apiPut<LaborParams>('/v1/neoffice/labor-tariff/params/', p),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['neoffice'] });
      addToast({
        type: 'success',
        title: t('settings.labor_saved', { defaultValue: 'Paramètres main-d’œuvre enregistrés' }),
      });
    },
  });

  if (!form) return null;

  return (
    <Card className="lg:col-span-2">
      <CardHeader
        title={t('settings.labor_title', { defaultValue: 'Main-d’œuvre — paramètres du tarif' })}
        subtitle={t('settings.labor_subtitle', {
          defaultValue:
            "Calibrez la composition du coût horaire (salaire de base + ces paramètres + déplacement). Utilisé par le tarif composé et la carte déplacement des projets.",
        })}
      />
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FIELDS.map((f) => (
            <label key={f.key} className="flex flex-col gap-1">
              <span className="text-sm font-medium text-content-primary">
                {t(`settings.labor_${f.key}`, { defaultValue: f.label })}
              </span>
              <input
                type="text"
                inputMode="decimal"
                value={form[f.key]}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                className="rounded-lg border border-border-light bg-surface-secondary px-3 py-2 text-sm tabular-nums focus:border-oe-blue focus:outline-none"
              />
              <span className="text-2xs text-content-tertiary">{f.hint}</span>
            </label>
          ))}
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
