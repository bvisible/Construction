# Backend patches — Neoconstruction

> Patches Neoservice appliqués au backend OCE upstream sur les déploiements
> Neoconstruction. Format `git diff` — chaque `.patch` peut être appliqué
> avec `git apply` depuis la racine du fork.
>
> **Source de vérité** : `Neoffice/Neoconstruction/25-Patches-OCE-Inventory.md`
> dans le vault Obsidian. Mettre les deux en cohérence.

## Inventaire

| # | Fichier patch | Cible upstream | Description courte | Plan retrait |
|---|---------------|----------------|---------------------|--------------|
| 01 | `01-ai-init-olares-default.patch` | `app/modules/ai/__init__.py` | Enregistre les permissions AI à l'import time (workaround : `on_startup()` n'est jamais appelé par le bootstrap FastAPI dans ce fork → `RequirePermission` deny par défaut) | À retirer si OCE wire correctement le hook `on_startup` |
| 02 | `02-ai-client-gate-unblock.patch` | `app/modules/ai/ai_client.py` | (a) helper `_read_frappe_site_config()` ; (b) enregistrement Olares comme provider OpenAI-compatible ; (c) override `resolve_provider_and_key()` pour forcer Olares quand `oce_olares_api_key` est présent | Permanent (intégration NORA / Olares) |
| 03 | `03-ai-service-eager-perms.patch` | `app/modules/ai/service.py` | (a) rebrand `preferred_model` → `"NORA"` quand Olares actif ; (b) defaults CH (currency/standard/location) lus depuis Frappe `site_config.json` (`oce_default_currency`, `oce_default_standard`, `oce_default_location`) au lieu de `EUR` / `din276` / `Europe` upstream | (a) permanent rebrand ; (b) à retirer si on bouge les defaults dans la config OCE elle-même |
| 04 | `04-alembic-v290-boolean-pg.patch` | `alembic/versions/v290_dashboards_presets.py` | `sa.Boolean() server_default=sa.text("0")` → `text("false")` — bug upstream qui bloque tout déploiement Postgres | À retirer dès que upstream merge le fix (PR à ouvrir) |
| 05 | `05-alembic-v2a0-boolean-pg.patch` | `alembic/versions/v2a0_compliance_dsl_rules.py` | Idem 04 mais sur la colonne `is_active` | Idem 04 |
| 06 | `06-bim-hub-import-date-string.patch` | `app/modules/bim_hub/router.py` | `model.import_date = _dt.now(_UTC)` → `.isoformat()[:20]`. La colonne est `VARCHAR(20)` mais le code assigne un `datetime.datetime` → asyncpg rejette → **tous les uploads IFC/CAD échouent en mode `error` après la conversion DDC**. Découvert 2026-05-16 en testant `/bim` avec `Building-Architecture.ifc` (status `error` après extraction de 19 éléments). | Permanent jusqu'à fix upstream — à reporter |

## Application

```bash
# Depuis la racine du fork OCE (/Users/jeremy/GitHub/Construction)
for p in backend-patches/*.patch; do
  echo "Applying $p..."
  git apply --check "$p" && git apply "$p" || echo "FAILED: $p"
done
```

Les patches doivent être ré-appliqués après chaque `git merge upstream/vX.Y.Z`
qui touche les fichiers ciblés. Le script `scripts/apply-backend-patches.sh`
(à créer — équivalent backend de `apply-frontend-patches.sh`) doit automatiser
ça en mode idempotent.

## Pourquoi le format `.patch` plutôt que des commits ?

À court terme (mai 2026), on conserve les patches comme `.patch` pour deux
raisons :

1. **Lisibilité** — chaque patch est un fichier autonome qu'on peut auditer en
   un coup d'œil sans `git log`.
2. **Application sélective** — on peut appliquer 4/5 patches sur un déploiement
   particulier (ex : un dev environnement sans Olares peut sauter le 02).

À moyen terme on **doit** migrer vers des commits versionnés sur la branche
`frappe-integration` du fork, dès qu'on a 5+ patches stables. Les `.patch`
deviennent alors auto-générés depuis l'historique git :

```bash
git format-patch upstream/vX.Y.Z..frappe-integration --output-directory=backend-patches/
```

## Cadence de revue

À chaque upgrade upstream :

1. Vérifier que tous les patches s'appliquent encore (`git apply --check`)
2. Si un patch ne s'applique plus → conflit avec une modif upstream → résoudre
   manuellement et **régénérer** le `.patch`
3. Vérifier si le patch est **devenu inutile** (upstream a intégré le fix /
   exposé un hook propre) → supprimer le `.patch` et mettre à jour la note 25
